import type { SessionDetailResponse, WebChatMessage } from '~/types/web-chat'

export type SessionMessageUpdateMode = 'append' | 'replace'

export function applySessionMessageUpdate(
  snapshot: SessionDetailResponse,
  message: WebChatMessage,
  mode: SessionMessageUpdateMode
): SessionDetailResponse {
  const matchesMessage = (candidate: WebChatMessage) => (
    candidate.id === message.id
    || Boolean(message.clientMessageId && candidate.clientMessageId === message.clientMessageId)
  )
  const existingIndex = snapshot.messages.findIndex(matchesMessage)

  if (existingIndex >= 0) {
    const messages = [...snapshot.messages]
    messages[existingIndex] = mode === 'replace' ? message : { ...messages[existingIndex], ...message }
    return { ...snapshot, messages }
  }

  if (mode === 'replace') return snapshot

  return {
    ...snapshot,
    messages: [...snapshot.messages, message],
    messagesTotal: typeof snapshot.messagesTotal === 'number' ? snapshot.messagesTotal + 1 : snapshot.messagesTotal
  }
}
