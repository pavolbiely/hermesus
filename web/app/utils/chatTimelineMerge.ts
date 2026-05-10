import type { WebChatMessage } from '~/types/web-chat'

function clientMessageId(message: WebChatMessage) {
  return message.clientMessageId || null
}

function turnId(message: WebChatMessage) {
  return message.turnId || message.runId || null
}

function hasEquivalentPersistedMessage(messages: WebChatMessage[], optimistic: WebChatMessage) {
  const optimisticClientId = clientMessageId(optimistic)
  return Boolean(optimisticClientId && messages.some(message => clientMessageId(message) === optimisticClientId))
}

function sameUserTurn(left: WebChatMessage, right: WebChatMessage) {
  const leftTurnId = turnId(left)
  const rightTurnId = turnId(right)
  return Boolean(leftTurnId && rightTurnId && leftTurnId === rightTurnId)
}

function previousUserMessage(messages: WebChatMessage[], message: WebChatMessage) {
  const messageIndex = messages.findIndex(candidate => candidate.id === message.id)
  if (messageIndex <= 0) return null

  for (let index = messageIndex - 1; index >= 0; index -= 1) {
    const candidate = messages[index]
    if (candidate?.role === 'user') return candidate
  }

  return null
}

function hasPersistedAssistantForSameTurn(
  persistedMessages: WebChatMessage[],
  currentMessages: WebChatMessage[],
  assistant: WebChatMessage
) {
  const assistantTurnId = turnId(assistant)
  if (!assistantTurnId) return false

  return persistedMessages.some(message => message.role === 'assistant' && turnId(message) === assistantTurnId)
}

function insertAfterCurrentTurnUser(
  messages: WebChatMessage[],
  currentMessages: WebChatMessage[],
  message: WebChatMessage
) {
  const currentUser = previousUserMessage(currentMessages, message)
  if (!currentUser) {
    messages.push(message)
    return
  }

  const userIndex = messages.findIndex(candidate => candidate.role === 'user' && sameUserTurn(candidate, currentUser))
  if (userIndex < 0) {
    messages.push(message)
    return
  }

  messages.splice(userIndex + 1, 0, message)
}

type MergeOptimisticUserMessagesOptions = {
  preserveStreamingAssistant?: boolean
  preserveAssistantMessageIds?: Set<string>
}

type MergeOptimisticUserMessagesResult = {
  messages: WebChatMessage[]
  optimisticMessageIds: Set<string>
  preservedAssistantMessageIds: Set<string>
}

function isPreservableAssistantMessage(message: WebChatMessage) {
  return message.role === 'assistant' && message.parts.length > 0 && Boolean(turnId(message))
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

export function mergeChatTimeline(
  persistedMessages: WebChatMessage[],
  currentMessages: WebChatMessage[],
  optimisticMessageIds: Set<string>,
  options: MergeOptimisticUserMessagesOptions = {}
): MergeOptimisticUserMessagesResult {
  const nextMessages = [...persistedMessages]
  const nextOptimisticIds = new Set(optimisticMessageIds)
  const nextPreservedAssistantIds = new Set(options.preserveAssistantMessageIds || [])
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

    const preserveAssistant = isPreservableAssistantMessage(message)
      && !persistedIds.has(message.id)
      && (options.preserveStreamingAssistant || nextPreservedAssistantIds.has(message.id))

    if (preserveAssistant) {
      if (
        nextPreservedAssistantIds.has(message.id)
        && (
          hasPersistedAssistantForSameTurn(persistedMessages, currentMessages, message)
        )
      ) {
        nextPreservedAssistantIds.delete(message.id)
        continue
      }
      insertAfterCurrentTurnUser(nextMessages, currentMessages, message)
    } else if (!persistedIds.has(message.id) && isLocalSystemEventMessage(message) && !hasEquivalentSystemEvent(nextMessages, message)) {
      nextMessages.push(message)
    }
  }

  for (const messageId of Array.from(nextPreservedAssistantIds)) {
    if (!nextMessages.some(message => message.id === messageId)) nextPreservedAssistantIds.delete(messageId)
  }

  return {
    messages: nextMessages,
    optimisticMessageIds: nextOptimisticIds,
    preservedAssistantMessageIds: nextPreservedAssistantIds
  }
}
