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

type MergeOptimisticUserMessagesOptions = {
  preserveStreamingAssistant?: boolean
}

function isStreamingAssistantMessage(message: WebChatMessage) {
  return message.role === 'assistant' && message.parts.length > 0
}

function isLocalSystemEventMessage(message: WebChatMessage) {
  return message.role === 'system' && message.parts.some(part => part.type === 'event')
}

function systemEventKey(message: WebChatMessage) {
  const event = message.parts.find(part => part.type === 'event')
  if (!event) return null
  return [event.eventType || '', event.title || '', event.description || '', event.text || ''].join('\u0000')
}

function hasEquivalentSystemEvent(messages: WebChatMessage[], message: WebChatMessage) {
  const key = systemEventKey(message)
  return Boolean(key && messages.some(candidate => systemEventKey(candidate) === key))
}

export function mergeOptimisticUserMessages(
  persistedMessages: WebChatMessage[],
  currentMessages: WebChatMessage[],
  optimisticMessageIds: Set<string>,
  options: MergeOptimisticUserMessagesOptions = {}
) {
  const nextMessages = [...persistedMessages]
  const nextOptimisticIds = new Set(optimisticMessageIds)
  const persistedIds = new Set(persistedMessages.map(message => message.id))

  for (const message of currentMessages) {
    if (nextOptimisticIds.has(message.id)) {
      if (message.role !== 'user') {
        nextOptimisticIds.delete(message.id)
        continue
      }
      if (persistedIds.has(message.id) || hasEquivalentPersistedMessage(persistedMessages, message)) {
        nextOptimisticIds.delete(message.id)
        continue
      }

      nextMessages.push(message)
      continue
    }

    if (options.preserveStreamingAssistant && !persistedIds.has(message.id) && isStreamingAssistantMessage(message)) {
      nextMessages.push(message)
    } else if (!persistedIds.has(message.id) && isLocalSystemEventMessage(message) && !hasEquivalentSystemEvent(nextMessages, message)) {
      nextMessages.push(message)
    }
  }

  return { messages: nextMessages, optimisticMessageIds: nextOptimisticIds }
}
