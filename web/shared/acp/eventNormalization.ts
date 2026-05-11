import type { AcpChatEvent, AcpChatMessage, AcpTranscriptState, AcpTurnContext } from './types'

export function createAcpTurnContext(sessionId: string, turnId = crypto.randomUUID(), createdAt = new Date().toISOString()): AcpTurnContext {
  return { sessionId, turnId, createdAt }
}

export function createEmptyAcpTranscriptState(): AcpTranscriptState {
  return { messages: [], seenEventIds: new Set() }
}

export function applyAcpChatEvent(state: AcpTranscriptState, event: AcpChatEvent): AcpTranscriptState {
  if (hasSeenEvent(state, event) || isOlderThanSnapshot(state, event)) return cloneState(state)

  if (event.type === 'transcript.loaded') {
    return {
      messages: event.messages.map(cloneMessage),
      cursor: event.cursor ?? state.cursor,
      seenEventIds: nextSeenEventIds(state, event)
    }
  }

  const next = cloneState(state)
  rememberEvent(next, event)

  switch (event.type) {
    case 'user.message':
      upsertTurnMessage(next.messages, {
        sessionId: event.sessionId,
        turnId: event.turnId,
        role: 'user',
        messageId: event.messageId,
        fallbackId: `user-${event.turnId}`,
        occurredAt: event.occurredAt,
        text: event.text
      })
      break
    case 'user.message.delta':
      upsertTurnMessage(next.messages, {
        sessionId: event.sessionId,
        turnId: event.turnId,
        role: 'user',
        messageId: event.messageId,
        fallbackId: `user-${event.turnId}`,
        occurredAt: event.occurredAt,
        text: event.text,
        append: true
      })
      break
    case 'message.delta':
      upsertTurnMessage(next.messages, {
        sessionId: event.sessionId,
        turnId: event.turnId,
        role: 'assistant',
        messageId: event.messageId,
        fallbackId: `assistant-${event.turnId}`,
        occurredAt: event.occurredAt,
        text: event.text,
        append: true
      })
      break
    case 'reasoning.delta':
      upsertAssistantPart(next.messages, event, { type: 'reasoning', text: event.text })
      break
    case 'tool.started':
      upsertToolPart(next.messages, event, {
        type: 'tool',
        toolCallId: event.toolCallId,
        name: event.name,
        kind: event.kind,
        status: event.status,
        locations: event.locations,
        input: event.input,
        output: event.output,
        state: toolState(event.status)
      })
      break
    case 'tool.updated':
      updateToolPart(next.messages, event)
      break
    case 'tool.completed':
      completeToolPart(next.messages, event)
      break
    case 'message.completed':
      adoptAssistantMessageCompletion(next.messages, event)
      break
    case 'run.failed':
      upsertAssistantPart(next.messages, event, { type: 'event', title: event.message, severity: 'error' })
      break
    case 'permission.requested':
      break
    case 'run.completed':
      completeOpenToolParts(next.messages, event.turnId)
      break
  }

  if (event.sequence !== undefined) next.cursor = Math.max(next.cursor ?? event.sequence, event.sequence)
  return next
}

function hasSeenEvent(state: AcpTranscriptState, event: AcpChatEvent) {
  return Boolean(event.eventId && state.seenEventIds.has(event.eventId))
}

function isOlderThanSnapshot(state: AcpTranscriptState, event: AcpChatEvent) {
  if (event.sequence === undefined || state.cursor === undefined) return false
  if (event.sequence < state.cursor) return true
  if (event.sequence > state.cursor) return false

  // A single bridge event can expand into multiple chat events with the same
  // source sequence. Allow later siblings from the same source event to apply
  // after the first one advances the cursor, while still skipping sequence-equal
  // replay events after a transcript snapshot load.
  return !hasSeenSequenceSibling(state, event)
}

function hasSeenSequenceSibling(state: AcpTranscriptState, event: AcpChatEvent) {
  const prefix = `${event.sessionId}:${event.sequence}:`
  return Array.from(state.seenEventIds).some(eventId => eventId.startsWith(prefix))
}

function nextSeenEventIds(state: AcpTranscriptState, event: AcpChatEvent) {
  const seen = new Set(state.seenEventIds)
  if (event.eventId) seen.add(event.eventId)
  return seen
}

function rememberEvent(state: AcpTranscriptState, event: AcpChatEvent) {
  if (event.eventId) state.seenEventIds.add(event.eventId)
}

function cloneState(state: AcpTranscriptState): AcpTranscriptState {
  return {
    messages: state.messages.map(cloneMessage),
    cursor: state.cursor,
    seenEventIds: new Set(state.seenEventIds)
  }
}

function cloneMessage(message: AcpChatMessage): AcpChatMessage {
  return {
    ...message,
    parts: message.parts.map(part => ({ ...part }))
  }
}

function upsertTurnMessage(
  messages: AcpChatMessage[],
  options: {
    sessionId: string
    turnId: string
    role: 'user' | 'assistant'
    messageId?: string
    fallbackId: string
    occurredAt?: string
    text: string
    append?: boolean
  }
) {
  const existing = findTurnMessage(messages, options.role, options.turnId, options.messageId)
  if (!existing) {
    insertTurnMessage(messages, {
      id: options.messageId ?? options.fallbackId,
      role: options.role,
      sessionId: options.sessionId,
      turnId: options.turnId,
      createdAt: options.occurredAt ?? new Date().toISOString(),
      parts: options.text ? [{ type: 'text', text: options.text }] : []
    })
    return
  }

  if (options.messageId) existing.id = options.messageId
  const textPart = existing.parts.find(part => part.type === 'text')
  if (!textPart) {
    existing.parts.unshift({ type: 'text', text: options.text })
  } else if (options.append) {
    textPart.text += options.text
  } else {
    textPart.text = options.text
  }
}

function upsertAssistantPart(messages: AcpChatMessage[], event: { sessionId: string, turnId: string, occurredAt?: string }, part: AcpChatMessage['parts'][number]) {
  const message = ensureAssistantMessage(messages, event)
  message.parts.push(part)
}

function upsertToolPart(messages: AcpChatMessage[], event: { sessionId: string, turnId: string, occurredAt?: string }, part: Extract<AcpChatMessage['parts'][number], { type: 'tool' }>) {
  const message = ensureAssistantMessage(messages, event)
  const existing = message.parts.find(item => item.type === 'tool' && item.toolCallId === part.toolCallId)
  if (existing?.type === 'tool') {
    if (shouldAdoptToolName(existing.name, part.name, part.toolCallId, part.kind)) existing.name = part.name!
    else existing.name ||= part.toolCallId
    existing.kind = part.kind ?? existing.kind
    existing.status = part.status ?? existing.status
    existing.locations = part.locations ?? existing.locations
    existing.input = part.input ?? existing.input
    existing.output = part.output ?? existing.output
    existing.error = part.error ?? existing.error
    existing.state = part.state
    return
  }

  message.parts.push(part)
}

function updateToolPart(messages: AcpChatMessage[], event: { sessionId: string, turnId: string, toolCallId: string, name?: string, kind?: string, status?: string, locations?: Extract<AcpChatMessage['parts'][number], { type: 'tool' }>['locations'], input?: unknown, output?: unknown, error?: string | null, occurredAt?: string }) {
  const state = toolState(event.status, event.error)
  upsertToolPart(messages, event, {
    type: 'tool',
    toolCallId: event.toolCallId,
    name: event.name ?? event.toolCallId,
    kind: event.kind,
    status: event.status,
    locations: event.locations,
    input: event.input,
    output: event.output,
    error: event.error,
    state
  })
}

function completeToolPart(messages: AcpChatMessage[], event: { sessionId: string, turnId: string, toolCallId: string, name?: string, kind?: string, status?: string, locations?: Extract<AcpChatMessage['parts'][number], { type: 'tool' }>['locations'], input?: unknown, output?: unknown, error?: string | null, occurredAt?: string }) {
  const message = ensureAssistantMessage(messages, event)
  const existing = message.parts.find(part => part.type === 'tool' && part.toolCallId === event.toolCallId)
  if (existing?.type === 'tool') {
    if (shouldAdoptToolName(existing.name, event.name, event.toolCallId, event.kind)) existing.name = event.name!
    else existing.name ||= event.toolCallId
    existing.kind = event.kind ?? existing.kind
    existing.status = event.status ?? existing.status ?? (event.error ? 'failed' : 'completed')
    existing.locations = event.locations ?? existing.locations
    existing.input = event.input ?? existing.input
    existing.output = event.output ?? existing.output
    existing.error = event.error ?? existing.error
    existing.state = 'completed'
    return
  }

  message.parts.push({
    type: 'tool',
    toolCallId: event.toolCallId,
    name: event.name ?? event.toolCallId,
    kind: event.kind,
    status: event.status ?? (event.error ? 'failed' : 'completed'),
    locations: event.locations,
    input: event.input,
    output: event.output,
    error: event.error,
    state: 'completed'
  })
}

function shouldAdoptToolName(current: string | undefined, next: string | undefined, toolCallId: string, kind?: string) {
  if (!next || next === toolCallId) return false
  if (current && kind && next === kind && current !== kind) return false
  return true
}

function toolState(status?: string, error?: string | null): 'started' | 'completed' {
  if (error || status === 'completed' || status === 'failed') return 'completed'
  return 'started'
}

function completeOpenToolParts(messages: AcpChatMessage[], turnId: string) {
  const message = findTurnMessage(messages, 'assistant', turnId)
  if (!message) return

  for (const part of message.parts) {
    if (part.type === 'tool' && part.state !== 'completed') {
      part.state = 'completed'
      part.status = part.status === 'failed' ? part.status : 'completed'
    }
  }
}

function ensureAssistantMessage(messages: AcpChatMessage[], event: { sessionId: string, turnId: string, occurredAt?: string }) {
  let message = findTurnMessage(messages, 'assistant', event.turnId)
  if (!message) {
    message = {
      id: `assistant-${event.turnId}`,
      role: 'assistant',
      sessionId: event.sessionId,
      turnId: event.turnId,
      createdAt: event.occurredAt ?? new Date().toISOString(),
      parts: []
    }
    insertTurnMessage(messages, message)
  }
  return message
}

function insertTurnMessage(messages: AcpChatMessage[], message: AcpChatMessage) {
  const sameTurnIndexes = messages
    .map((item, index) => item.turnId === message.turnId ? index : -1)
    .filter(index => index >= 0)

  if (!sameTurnIndexes.length) {
    messages.push(message)
    return
  }

  const firstIndex = sameTurnIndexes[0]
  const lastIndex = sameTurnIndexes[sameTurnIndexes.length - 1]
  if (firstIndex === undefined || lastIndex === undefined) {
    messages.push(message)
    return
  }

  if (message.role === 'assistant') {
    messages.splice(lastIndex + 1, 0, message)
    return
  }

  messages.splice(firstIndex, 0, message)
}

function findTurnMessage(messages: AcpChatMessage[], role: 'user' | 'assistant', turnId: string, messageId?: string) {
  return messages.find(message => {
    if (message.role !== role) return false
    if (messageId && message.id === messageId) return true
    return message.turnId === turnId
  })
}

function adoptAssistantMessageCompletion(messages: AcpChatMessage[], event: { turnId: string, messageId?: string, userMessageId?: string, occurredAt?: string, usage?: AcpChatMessage['usage'] }) {
  const message = findTurnMessage(messages, 'assistant', event.turnId)
    ?? findAssistantAfterUserMessage(messages, event.userMessageId)
  if (!message) return
  if (event.messageId && message.turnId === event.turnId) message.id = event.messageId
  message.completedAt = event.occurredAt ?? new Date().toISOString()
  if (event.usage) message.usage = event.usage
}

function findAssistantAfterUserMessage(messages: AcpChatMessage[], userMessageId?: string) {
  if (!userMessageId) return undefined
  const userIndex = messages.findIndex(message => message.role === 'user' && message.id === userMessageId)
  if (userIndex === -1) return undefined
  return messages.slice(userIndex + 1).find(message => message.role === 'assistant')
}
