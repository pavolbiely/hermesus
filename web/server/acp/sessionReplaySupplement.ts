import type { AcpBridgeEvent } from '../../shared/acp/types'

export type ReplaySessionMessage = {
  role?: string
  content?: unknown
}

export function supplementMissingTranscriptEvents(sessionId: string, messages: ReplaySessionMessage[], replayedEvents: AcpBridgeEvent[]): AcpBridgeEvent[] {
  const replayed = replayedTextQueues(replayedEvents)
  const nextEvents: AcpBridgeEvent[] = []
  let currentTurnId: string | undefined
  let nextSequence = Math.max(0, ...replayedEvents.map(event => event.sequence ?? 0)) + 1

  messages.forEach((message, index) => {
    if (message.role !== 'user' && message.role !== 'assistant') return
    const text = textFromSessionContent(message.content)
    if (!text) return

    const replayedEvent = shiftReplayedEvent(replayed, message.role, text)
    if (message.role === 'user') {
      currentTurnId = replayedEvent?.turnId ?? rawReplayTurnId(sessionId, index)
    }
    if (replayedEvent) return
    if (message.role !== 'user') return

    const turnId = currentTurnId ?? rawReplayTurnId(sessionId, index)
    const messageId = `${message.role === 'user' ? 'raw-replay-user' : 'raw-replay-assistant'}:${index}`
    nextEvents.push({
      type: 'session.update',
      sessionId,
      turnId,
      messageId,
      sequence: nextSequence++,
      notification: {
        sessionId,
        update: {
          sessionUpdate: message.role === 'user' ? 'user_message_chunk' : 'agent_message_chunk',
          content: { type: 'text', text },
          messageId
        }
      }
    })
  })

  return nextEvents
}

function replayedTextQueues(events: AcpBridgeEvent[]) {
  const queues = new Map<string, Extract<AcpBridgeEvent, { type: 'session.update' }>[]>()
  for (const event of events) {
    if (event.type !== 'session.update') continue
    const update = event.notification.update as Record<string, unknown>
    const role = update.sessionUpdate === 'user_message_chunk' ? 'user' : update.sessionUpdate === 'agent_message_chunk' ? 'assistant' : null
    if (!role) continue
    const text = textFromBridgeContent(update.content)
    if (!text) continue
    const key = replayedTextKey(role, text)
    queues.set(key, [...(queues.get(key) ?? []), event])
  }
  return queues
}

function shiftReplayedEvent(queues: Map<string, Extract<AcpBridgeEvent, { type: 'session.update' }>[]>, role: 'user' | 'assistant', text: string) {
  const queue = queues.get(replayedTextKey(role, text))
  return queue?.shift()
}

function replayedTextKey(role: 'user' | 'assistant', text: string) {
  return `${role}:${text}`
}

function rawReplayTurnId(sessionId: string, index: number) {
  return `${sessionId}:raw-replay-turn:${index}`
}

function textFromBridgeContent(content: unknown) {
  if (!content || typeof content !== 'object') return ''
  const record = content as Record<string, unknown>
  return typeof record.text === 'string' ? record.text : ''
}

function textFromSessionContent(content: unknown) {
  if (typeof content === 'string') return content
  if (!Array.isArray(content)) return ''
  return content.map((part) => {
    if (!part || typeof part !== 'object') return ''
    const record = part as Record<string, unknown>
    if (typeof record.text === 'string') return record.text
    const nested = record.content
    if (typeof nested === 'string') return nested
    if (nested && typeof nested === 'object') {
      const text = (nested as Record<string, unknown>).text
      return typeof text === 'string' ? text : ''
    }
    return ''
  }).filter(Boolean).join('\n')
}
