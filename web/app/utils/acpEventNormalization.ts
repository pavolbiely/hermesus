import type { AcpChatEvent, AcpChatMessage, AcpTranscriptState, AcpTurnContext } from '~/types/acp-chat'

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
      upsertAssistantPart(next.messages, event, {
        type: 'tool',
        toolCallId: event.toolCallId,
        name: event.name,
        input: event.input,
        state: 'started'
      })
      break
    case 'tool.completed':
      completeToolPart(next.messages, event)
      break
    case 'message.completed':
      adoptAssistantMessageId(next.messages, event.turnId, event.messageId)
      break
    case 'run.failed':
      upsertAssistantPart(next.messages, event, { type: 'event', title: event.message, severity: 'error' })
      break
    case 'permission.requested':
    case 'run.completed':
      break
  }

  if (event.sequence !== undefined) next.cursor = Math.max(next.cursor ?? event.sequence, event.sequence)
  return next
}

function hasSeenEvent(state: AcpTranscriptState, event: AcpChatEvent) {
  return Boolean(event.eventId && state.seenEventIds.has(event.eventId))
}

function isOlderThanSnapshot(state: AcpTranscriptState, event: AcpChatEvent) {
  return event.sequence !== undefined && state.cursor !== undefined && event.sequence <= state.cursor
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

function completeToolPart(messages: AcpChatMessage[], event: { sessionId: string, turnId: string, toolCallId: string, name?: string, output?: unknown, error?: string | null, occurredAt?: string }) {
  const message = ensureAssistantMessage(messages, event)
  const existing = message.parts.find(part => part.type === 'tool' && part.toolCallId === event.toolCallId)
  if (existing?.type === 'tool') {
    existing.name = event.name ?? existing.name
    existing.output = event.output
    existing.error = event.error
    existing.state = 'completed'
    return
  }

  message.parts.push({
    type: 'tool',
    toolCallId: event.toolCallId,
    name: event.name ?? event.toolCallId,
    output: event.output,
    error: event.error,
    state: 'completed'
  })
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

function adoptAssistantMessageId(messages: AcpChatMessage[], turnId: string, messageId?: string) {
  if (!messageId) return
  const message = findTurnMessage(messages, 'assistant', turnId)
  if (message) message.id = messageId
}
