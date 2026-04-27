import type { WebChatMessage } from '~/types/web-chat'

function textParts(message: WebChatMessage) {
  return message.parts
    .filter(part => part.type === 'text')
    .map(part => part.text || '')
    .join('\n\n')
}

function messageTime(message: WebChatMessage) {
  const time = new Date(message.createdAt).getTime()
  return Number.isFinite(time) ? time : 0
}

function clientMessageId(message: WebChatMessage) {
  return message.clientMessageId || null
}

function hasEquivalentPersistedMessage(messages: WebChatMessage[], optimistic: WebChatMessage) {
  const optimisticClientId = clientMessageId(optimistic)
  if (optimisticClientId && messages.some(message => clientMessageId(message) === optimisticClientId)) {
    return true
  }

  const optimisticText = textParts(optimistic)
  if (!optimisticText) return false

  const optimisticTime = messageTime(optimistic)
  return messages.some(message => (
    message.role === optimistic.role
    && textParts(message) === optimisticText
    && messageTime(message) >= optimisticTime
  ))
}

export function mergeOptimisticUserMessages(
  persistedMessages: WebChatMessage[],
  currentMessages: WebChatMessage[],
  optimisticMessageIds: Set<string>
) {
  const nextMessages = [...persistedMessages]
  const nextOptimisticIds = new Set(optimisticMessageIds)
  const persistedIds = new Set(persistedMessages.map(message => message.id))

  for (const message of currentMessages) {
    if (!nextOptimisticIds.has(message.id)) continue
    if (message.role !== 'user') {
      nextOptimisticIds.delete(message.id)
      continue
    }
    if (persistedIds.has(message.id) || hasEquivalentPersistedMessage(persistedMessages, message)) {
      nextOptimisticIds.delete(message.id)
      continue
    }

    nextMessages.push(message)
  }

  return { messages: nextMessages, optimisticMessageIds: nextOptimisticIds }
}
