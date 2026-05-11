import type { PermissionOption } from '~/types/acp-api'

export type AcpChatRole = 'user' | 'assistant' | 'system'

export type AcpChatPart =
  | { type: 'text', text: string }
  | { type: 'reasoning', text: string }
  | { type: 'tool', toolCallId: string, name: string, input?: unknown, output?: unknown, error?: string | null, state: 'started' | 'completed' }
  | { type: 'event', title: string, severity?: 'info' | 'warning' | 'error' }

export type AcpChatMessage = {
  id: string
  role: AcpChatRole
  sessionId: string
  turnId?: string
  createdAt: string
  parts: AcpChatPart[]
}

export type AcpTurnContext = {
  sessionId: string
  turnId: string
  createdAt: string
}

export type AcpChatEventBase = {
  eventId?: string
  sessionId: string
  turnId?: string
  sequence?: number
  occurredAt?: string
}

export type AcpChatEvent =
  | (AcpChatEventBase & { type: 'transcript.loaded', cursor?: number, messages: AcpChatMessage[] })
  | (AcpChatEventBase & { type: 'user.message', turnId: string, messageId?: string, text: string })
  | (AcpChatEventBase & { type: 'user.message.delta', turnId: string, messageId?: string, text: string })
  | (AcpChatEventBase & { type: 'message.delta', turnId: string, messageId?: string, text: string })
  | (AcpChatEventBase & { type: 'reasoning.delta', turnId: string, text: string })
  | (AcpChatEventBase & { type: 'tool.started', turnId: string, toolCallId: string, name: string, input?: unknown })
  | (AcpChatEventBase & { type: 'tool.completed', turnId: string, toolCallId: string, name?: string, output?: unknown, error?: string | null })
  | (AcpChatEventBase & { type: 'message.completed', turnId: string, messageId?: string })
  | (AcpChatEventBase & { type: 'permission.requested', requestId: string, options: PermissionOption[] })
  | (AcpChatEventBase & { type: 'run.completed', turnId: string })
  | (AcpChatEventBase & { type: 'run.failed', turnId: string, message: string })

export type AcpTranscriptState = {
  messages: AcpChatMessage[]
  cursor?: number
  seenEventIds: Set<string>
}
