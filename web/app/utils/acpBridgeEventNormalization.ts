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
      input: update.rawInput,
      occurredAt
    }]
  }

  if (sessionUpdate === 'tool_call_update') {
    const id = toolCallId(update)
    if (!id) return []
    return [{
      type: 'tool.completed',
      eventId: eventId(event, `${sessionUpdate}:${id}`),
      sessionId: event.sessionId,
      turnId: event.turnId ?? turnIdFromUpdate(event.sessionId, update, 'tool'),
      toolCallId: id,
      name: toolCallName(update, id),
      output: update.content ?? update.rawOutput,
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
