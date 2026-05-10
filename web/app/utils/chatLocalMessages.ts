import type { WebChatMessage } from '~/types/web-chat'

export function createLocalMessage(role: WebChatMessage['role'], text: string): WebChatMessage {
  return {
    id: crypto.randomUUID(),
    role,
    createdAt: new Date().toISOString(),
    parts: text ? [{ type: 'text', text }] : []
  }
}
