import type { WebChatMessage } from '~/types/web-chat'

type ChatMessagesStatus = 'ready' | 'submitted' | 'streaming' | 'error'

type ActivityIndicatorOptions = {
  messages: WebChatMessage[]
  status: ChatMessagesStatus
}

export function shouldShowNativeActivityIndicator(options: ActivityIndicatorOptions) {
  if (options.status === 'submitted') return true
  if (options.status !== 'streaming') return false

  const lastMessage = options.messages.at(-1)
  return lastMessage?.role === 'assistant' && !lastMessage.parts?.length
}

export function shouldShowStandaloneActivityIndicator(options: ActivityIndicatorOptions & { showRunActivityIndicator: boolean }) {
  return options.showRunActivityIndicator && !shouldShowNativeActivityIndicator(options)
}
