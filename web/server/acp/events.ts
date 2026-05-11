import type { AcpBridgeEvent } from '../../shared/acp/types'

export type { AcpBridgeEvent }

export type AcpEventSubscriber = (event: AcpBridgeEvent) => void

const sessionSubscribers = new Map<string, Set<AcpEventSubscriber>>()
const replayCaptureSubscribers = new Map<string, Set<AcpEventSubscriber>>()
const replayCaptureDepth = new Map<string, number>()
const sessionBacklog = new Map<string, AcpBridgeEvent[]>()
const sessionSequence = new Map<string, number>()
const maxBacklogEvents = 200

function nextSequence(sessionId: string) {
  const sequence = (sessionSequence.get(sessionId) ?? 0) + 1
  sessionSequence.set(sessionId, sequence)
  return sequence
}

export function ensureAcpSessionSequenceAtLeast(sessionId: string, sequence: number | undefined) {
  if (sequence === undefined || !Number.isFinite(sequence)) return
  const current = sessionSequence.get(sessionId) ?? 0
  if (sequence > current) sessionSequence.set(sessionId, sequence)
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
  if ((replayCaptureDepth.get(sequencedEvent.sessionId) ?? 0) > 0) {
    const captureSubscribers = replayCaptureSubscribers.get(sequencedEvent.sessionId)
    captureSubscribers?.forEach((subscriber) => {
      try {
        subscriber(sequencedEvent)
      } catch (error) {
        console.warn('ACP replay capture subscriber failed', error)
      }
    })
    return
  }

  rememberAcpEvent(sequencedEvent.sessionId, sequencedEvent)
  const subscribers = sessionSubscribers.get(sequencedEvent.sessionId)
  if (!subscribers) return
  subscribers.forEach((subscriber) => {
    try {
      subscriber(sequencedEvent)
    } catch (error) {
      console.warn('ACP event subscriber failed', error)
    }
  })
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

export function captureAcpSessionReplay(sessionId: string, subscriber: AcpEventSubscriber) {
  let subscribers = replayCaptureSubscribers.get(sessionId)
  if (!subscribers) {
    subscribers = new Set()
    replayCaptureSubscribers.set(sessionId, subscribers)
  }

  subscribers.add(subscriber)
  replayCaptureDepth.set(sessionId, (replayCaptureDepth.get(sessionId) ?? 0) + 1)

  return () => {
    subscribers.delete(subscriber)
    if (subscribers.size === 0) replayCaptureSubscribers.delete(sessionId)

    const nextDepth = (replayCaptureDepth.get(sessionId) ?? 1) - 1
    if (nextDepth > 0) replayCaptureDepth.set(sessionId, nextDepth)
    else replayCaptureDepth.delete(sessionId)
  }
}
