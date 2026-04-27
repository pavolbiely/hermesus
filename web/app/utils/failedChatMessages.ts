import type { WebChatMessage } from '~/types/web-chat'

export function markLocalMessageFailed(messages: WebChatMessage[], id: string, error: string) {
  return messages.map(message => message.id === id
    ? { ...message, localStatus: 'failed' as const, localError: error }
    : message
  )
}

export function markLocalMessageSending(messages: WebChatMessage[], id: string) {
  return messages.map(message => message.id === id
    ? { ...message, localStatus: 'sending' as const, localError: undefined }
    : message
  )
}

export function removeLocalMessage(messages: WebChatMessage[], id: string) {
  return messages.filter(message => message.id !== id)
}
