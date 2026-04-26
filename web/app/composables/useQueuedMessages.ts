import type { QueuedMessage } from '~/utils/queuedMessages'
import {
  createQueuedMessage,
  nextQueuedMessage,
  removeQueuedMessage,
  updateQueuedMessage
} from '~/utils/queuedMessages'

const STORAGE_KEY = 'hermesum:web-chat:queued-messages:v1'

function readStoredMessages(): QueuedMessage[] {
  if (!import.meta.client) return []

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    if (!Array.isArray(parsed)) return []
    return parsed.filter((message): message is QueuedMessage => (
      message
      && typeof message.id === 'string'
      && typeof message.sessionId === 'string'
      && typeof message.text === 'string'
      && typeof message.createdAt === 'string'
      && typeof message.updatedAt === 'string'
      && message.text.trim().length > 0
    ))
  } catch {
    return []
  }
}

export function useQueuedMessages() {
  const messages = useState<QueuedMessage[]>('web-chat-queued-messages', readStoredMessages)

  if (import.meta.client) {
    onMounted(() => {
      const stored = readStoredMessages()
      if (!stored.length) return

      const existingIds = new Set(messages.value.map(message => message.id))
      const restored = stored.filter(message => !existingIds.has(message.id))
      if (restored.length) messages.value = [...messages.value, ...restored]
    })

    watch(messages, (next) => {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    }, { deep: true })
  }

  function forSession(sessionId: string) {
    return messages.value.filter(message => message.sessionId === sessionId)
  }

  function enqueue(sessionId: string, text: string) {
    const message = createQueuedMessage({ sessionId, text })
    if (!message) return null
    messages.value = [...messages.value, message]
    return message
  }

  function prepend(message: QueuedMessage) {
    messages.value = [message, ...messages.value.filter(item => item.id !== message.id)]
  }

  function update(id: string, text: string) {
    messages.value = updateQueuedMessage(messages.value, id, text)
  }

  function remove(id: string) {
    messages.value = removeQueuedMessage(messages.value, id)
  }

  function nextForSession(sessionId: string) {
    return nextQueuedMessage(messages.value, sessionId)
  }

  function shiftForSession(sessionId: string) {
    const next = nextForSession(sessionId)
    if (next) remove(next.id)
    return next
  }

  function clearSession(sessionId: string) {
    messages.value = messages.value.filter(message => message.sessionId !== sessionId)
  }

  return {
    messages,
    forSession,
    enqueue,
    prepend,
    update,
    remove,
    nextForSession,
    shiftForSession,
    clearSession
  }
}
