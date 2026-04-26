export type QueuedMessage = {
  id: string
  sessionId: string
  text: string
  createdAt: string
  updatedAt: string
}

type CreateQueuedMessageOptions = {
  sessionId: string
  text: string
  id?: string
  now?: string
}

function newId() {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function createQueuedMessage(options: CreateQueuedMessageOptions): QueuedMessage | null {
  const text = options.text.trim()
  if (!text) return null

  const now = options.now || new Date().toISOString()
  return {
    id: options.id || newId(),
    sessionId: options.sessionId,
    text,
    createdAt: now,
    updatedAt: now
  }
}

export function updateQueuedMessage(messages: Array<QueuedMessage | null>, id: string, text: string, now = new Date().toISOString()): QueuedMessage[] {
  const trimmed = text.trim()
  if (!trimmed) return removeQueuedMessage(messages, id)

  return messages
    .filter((message): message is QueuedMessage => Boolean(message))
    .map(message => message.id === id ? { ...message, text: trimmed, updatedAt: now } : message)
}

export function removeQueuedMessage(messages: Array<QueuedMessage | null>, id: string): QueuedMessage[] {
  return messages
    .filter((message): message is QueuedMessage => Boolean(message))
    .filter(message => message.id !== id)
}

export function nextQueuedMessage(messages: Array<QueuedMessage | null>, sessionId: string): QueuedMessage | null {
  return messages
    .filter((message): message is QueuedMessage => Boolean(message))
    .find(message => message.sessionId === sessionId) || null
}
