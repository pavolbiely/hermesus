import type { SessionNotification } from '@agentclientprotocol/sdk'

export type AcpBridgeEvent =
  | { type: 'session.update', sessionId: string, sequence?: number, notification: SessionNotification, turnId?: string, messageId?: string }
  | { type: 'permission.requested', sessionId: string, sequence?: number, appRequestId: string, request: unknown }
  | { type: 'permission.resolved', sessionId: string, sequence?: number, appRequestId: string, response: unknown }
  | { type: 'prompt.started', sessionId: string, sequence?: number, turnId: string, messageId: string, message?: string }
  | { type: 'prompt.completed', sessionId: string, sequence?: number, turnId: string, messageId: string, response: unknown }
  | { type: 'prompt.failed', sessionId: string, sequence?: number, turnId: string, messageId: string, error: string }
  | { type: 'prompt.cancelled', sessionId: string, sequence?: number }

export type AcpEventSubscriber = (event: AcpBridgeEvent) => void

const sessionSubscribers = new Map<string, Set<AcpEventSubscriber>>()
const sessionBacklog = new Map<string, AcpBridgeEvent[]>()
const sessionSequence = new Map<string, number>()
const maxBacklogEvents = 200

function nextSequence(sessionId: string) {
  const sequence = (sessionSequence.get(sessionId) ?? 0) + 1
  sessionSequence.set(sessionId, sequence)
  return sequence
}

function withSequence(event: AcpBridgeEvent): AcpBridgeEvent {
  if (event.sequence !== undefined) return event
  return { ...event, sequence: nextSequence(event.sessionId) } as AcpBridgeEvent
}

function rememberAcpEvent(sessionId: string, event: AcpBridgeEvent) {
  const events = sessionBacklog.get(sessionId) ?? []
  events.push(event)
  if (events.length > maxBacklogEvents) events.splice(0, events.length - maxBacklogEvents)
  sessionBacklog.set(sessionId, events)
}

export function publishAcpEvent(event: AcpBridgeEvent) {
  const sequencedEvent = withSequence(event)
  rememberAcpEvent(sequencedEvent.sessionId, sequencedEvent)
  const subscribers = sessionSubscribers.get(sequencedEvent.sessionId)
  if (!subscribers) return
  subscribers.forEach(subscriber => subscriber(sequencedEvent))
}

export function replayAcpSession(sessionId: string) {
  return [...(sessionBacklog.get(sessionId) ?? [])]
}

export function subscribeAcpSession(sessionId: string, subscriber: AcpEventSubscriber) {
  let subscribers = sessionSubscribers.get(sessionId)
  if (!subscribers) {
    subscribers = new Set()
    sessionSubscribers.set(sessionId, subscribers)
  }

  subscribers.add(subscriber)

  return () => {
    subscribers.delete(subscriber)
    if (subscribers.size === 0) sessionSubscribers.delete(sessionId)
  }
}
