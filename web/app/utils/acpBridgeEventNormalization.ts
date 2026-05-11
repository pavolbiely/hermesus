import type { AcpBridgeEvent } from '~/types/acp-api'
import type { AcpChatEvent } from '~/types/acp-chat'

function eventId(event: AcpBridgeEvent, suffix: string) {
  if (event.sequence !== undefined) return `${event.sessionId}:${event.sequence}`
  if (event.type === 'prompt.started' || event.type === 'prompt.completed' || event.type === 'prompt.failed') {
    return `${event.type}:${event.turnId}:${suffix}`
  }
  if (event.type === 'prompt.cancelled') return `${event.type}:${event.sessionId}`
  if (event.type === 'permission.requested') return `${event.type}:${event.appRequestId}:${suffix}`
  return `${event.type}:${event.sessionId}:${suffix}`
}

function textFromContent(content: unknown) {
  if (!content || typeof content !== 'object') return ''
  const record = content as Record<string, unknown>
  return typeof record.text === 'string' ? record.text : ''
}

function toolCallId(update: Record<string, unknown>) {
  const value = update.toolCallId ?? update.id
  return typeof value === 'string' && value ? value : undefined
}

function toolCallName(update: Record<string, unknown>, fallback: string) {
  const value = update.title ?? update.name ?? update.kind
  return typeof value === 'string' && value ? value : fallback
}

function stringField(update: Record<string, unknown>, key: string) {
  const value = update[key]
  return typeof value === 'string' && value ? value : undefined
}

function toolCallOutput(update: Record<string, unknown>) {
  return update.content ?? update.rawOutput
}

function toolCallContentText(value: unknown) {
  if (!Array.isArray(value)) return undefined

  const text = value
    .map((item) => {
      if (!item || typeof item !== 'object') return ''
      const content = (item as Record<string, unknown>).content
      if (!content || typeof content !== 'object') return ''
      const text = (content as Record<string, unknown>).text
      return typeof text === 'string' ? text : ''
    })
    .filter(Boolean)
    .join('\n')
    .trim()

  return text || undefined
}

function toolCallInput(update: Record<string, unknown>) {
  return update.rawInput ?? toolCallContentText(update.content)
}

function toolCallLocations(update: Record<string, unknown>) {
  if (!Array.isArray(update.locations)) return undefined

  const locations = update.locations.flatMap((location) => {
    if (!location || typeof location !== 'object') return []
    const record = location as Record<string, unknown>
    if (typeof record.path !== 'string' || !record.path) return []
    return [{
      path: record.path,
      line: typeof record.line === 'number' ? record.line : null
    }]
  })

  return locations.length ? locations : undefined
}

function isTerminalToolStatus(status: string | undefined) {
  return status === 'completed' || status === 'failed'
}

function turnIdFromUpdate(sessionId: string, update: Record<string, unknown>, fallback: string) {
  const value = update.messageId ?? update.toolCallId ?? update.id
  return typeof value === 'string' && value ? value : `${sessionId}:${fallback}`
}

function normalizeSessionUpdate(event: Extract<AcpBridgeEvent, { type: 'session.update' }>): AcpChatEvent[] {
  const update = event.notification.update as Record<string, unknown>
  const sessionUpdate = update.sessionUpdate
  const occurredAt = new Date().toISOString()

  if (sessionUpdate === 'user_message_chunk' || sessionUpdate === 'agent_message_chunk') {
    const text = textFromContent(update.content)
    if (!text) return []
    const messageId = typeof update.messageId === 'string' ? update.messageId : undefined
    const turnId = event.turnId ?? messageId ?? `${event.sessionId}:${sessionUpdate === 'user_message_chunk' ? 'user' : 'agent'}`
    return [{
      type: sessionUpdate === 'user_message_chunk' ? 'user.message.delta' : 'message.delta',
      eventId: event.sequence !== undefined ? eventId(event, `${sessionUpdate}:${messageId ?? text}`) : undefined,
      sessionId: event.sessionId,
      turnId,
      messageId,
      sequence: event.sequence,
      occurredAt,
      text
    }]
  }

  if (sessionUpdate === 'agent_thought_chunk') {
    const text = textFromContent(update.content)
    if (!text) return []
    return [{
      type: 'reasoning.delta',
      eventId: eventId(event, `${sessionUpdate}:${text}`),
      sessionId: event.sessionId,
      turnId: event.turnId ?? turnIdFromUpdate(event.sessionId, update, 'thought'),
      occurredAt,
      text
    }]
  }

  if (sessionUpdate === 'tool_call') {
    const id = toolCallId(update)
    if (!id) return []
    return [{
      type: 'tool.started',
      eventId: eventId(event, `${sessionUpdate}:${id}`),
      sessionId: event.sessionId,
      turnId: event.turnId ?? turnIdFromUpdate(event.sessionId, update, 'tool'),
      toolCallId: id,
      name: toolCallName(update, id),
      kind: stringField(update, 'kind'),
      status: stringField(update, 'status') ?? 'pending',
      locations: toolCallLocations(update),
      input: toolCallInput(update),
      output: toolCallOutput(update),
      occurredAt
    }]
  }

  if (sessionUpdate === 'tool_call_update') {
    const id = toolCallId(update)
    if (!id) return []
    const status = stringField(update, 'status')
    const type = isTerminalToolStatus(status) || update.error ? 'tool.completed' : 'tool.updated'
    return [{
      type,
      eventId: eventId(event, `${sessionUpdate}:${id}:${status ?? update.error ?? update.content ?? update.rawOutput ?? 'update'}`),
      sessionId: event.sessionId,
      turnId: event.turnId ?? turnIdFromUpdate(event.sessionId, update, 'tool'),
      toolCallId: id,
      name: toolCallName(update, id),
      kind: stringField(update, 'kind'),
      status,
      locations: toolCallLocations(update),
      input: update.rawInput,
      output: toolCallOutput(update),
      error: typeof update.error === 'string' ? update.error : null,
      occurredAt
    }]
  }

  return []
}

export function normalizeAcpBridgeEvent(event: AcpBridgeEvent): AcpChatEvent[] {
  if (event.type === 'session.update') return normalizeSessionUpdate(event)

  if (event.type === 'prompt.started') {
    return [{
      type: 'user.message',
      eventId: eventId(event, 'user'),
      sessionId: event.sessionId,
      turnId: event.turnId,
      messageId: event.messageId,
      text: event.message ?? ''
    }]
  }

  if (event.type === 'prompt.completed') {
    return [
      {
        type: 'message.completed',
        eventId: eventId(event, 'assistant'),
        sessionId: event.sessionId,
        turnId: event.turnId
      },
      {
        type: 'run.completed',
        eventId: eventId(event, 'run'),
        sessionId: event.sessionId,
        turnId: event.turnId
      }
    ]
  }

  if (event.type === 'prompt.failed') {
    return [{
      type: 'run.failed',
      eventId: eventId(event, 'error'),
      sessionId: event.sessionId,
      turnId: event.turnId,
      message: event.error
    }]
  }

  if (event.type === 'permission.requested') {
    return [{
      type: 'permission.requested',
      eventId: eventId(event, 'permission'),
      sessionId: event.sessionId,
      requestId: event.appRequestId,
      options: event.request.options
    }]
  }

  if (event.type === 'permission.resolved') return []

  return []
}
