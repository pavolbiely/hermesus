import type {
  PermissionOption,
  PromptResponse,
  RequestPermissionRequest,
  RequestPermissionResponse,
  SessionNotification
} from '@agentclientprotocol/sdk'

export type AcpChatRole = 'user' | 'assistant' | 'system'

export type AcpToolCallStatus = 'pending' | 'in_progress' | 'completed' | 'failed' | string

export type AcpToolCallLocation = {
  path: string
  line?: number | null
}

export type AcpChatPart =
  | { type: 'text', text: string }
  | { type: 'reasoning', text: string }
  | { type: 'attachment', id?: string, name: string, mediaType: string, size?: number, data?: string }
  | { type: 'file', id?: string, filename: string, mediaType: string, size?: number, url: string }
  | { type: 'tool', toolCallId: string, name: string, kind?: string, status?: AcpToolCallStatus, locations?: AcpToolCallLocation[], input?: unknown, output?: unknown, error?: string | null, state: 'started' | 'completed' }
  | { type: 'event', title: string, severity?: 'info' | 'warning' | 'error' }

export type AcpAttachmentPart = Extract<AcpChatPart, { type: 'attachment' }>

export type AcpUsage = {
  totalTokens: number
  inputTokens: number
  outputTokens: number
  thoughtTokens?: number | null
  cachedReadTokens?: number | null
  cachedWriteTokens?: number | null
}

export type AcpChatMessage = {
  id: string
  role: AcpChatRole
  sessionId: string
  turnId?: string
  createdAt: string
  completedAt?: string
  usage?: AcpUsage | null
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
  | (AcpChatEventBase & { type: 'transcript.truncated', messageId: string })
  | (AcpChatEventBase & { type: 'user.message', turnId: string, messageId?: string, text: string, attachments?: AcpAttachmentPart[] })
  | (AcpChatEventBase & { type: 'user.message.delta', turnId: string, messageId?: string, text: string, attachments?: AcpAttachmentPart[] })
  | (AcpChatEventBase & { type: 'message.delta', turnId: string, messageId?: string, text: string })
  | (AcpChatEventBase & { type: 'reasoning.delta', turnId: string, text: string })
  | (AcpChatEventBase & { type: 'tool.started', turnId: string, toolCallId: string, name: string, kind?: string, status?: AcpToolCallStatus, locations?: AcpToolCallLocation[], input?: unknown, output?: unknown })
  | (AcpChatEventBase & { type: 'tool.updated', turnId: string, toolCallId: string, name?: string, kind?: string, status?: AcpToolCallStatus, locations?: AcpToolCallLocation[], input?: unknown, output?: unknown, error?: string | null })
  | (AcpChatEventBase & { type: 'tool.completed', turnId: string, toolCallId: string, name?: string, kind?: string, status?: AcpToolCallStatus, locations?: AcpToolCallLocation[], input?: unknown, output?: unknown, error?: string | null })
  | (AcpChatEventBase & { type: 'message.completed', turnId: string, messageId?: string, userMessageId?: string, usage?: AcpUsage | null })
  | (AcpChatEventBase & { type: 'permission.requested', requestId: string, options: PermissionOption[] })
  | (AcpChatEventBase & { type: 'run.completed', turnId: string })
  | (AcpChatEventBase & { type: 'run.failed', turnId: string, message: string })

export type AcpTranscriptState = {
  messages: AcpChatMessage[]
  cursor?: number
  seenEventIds: Set<string>
}

export type AcpBridgeEvent =
  | { type: 'session.update', sessionId: string, sequence?: number, notification: SessionNotification, turnId?: string, messageId?: string, userAttachments?: AcpAttachmentPart[] }
  | { type: 'transcript.truncated', sessionId: string, sequence?: number, messageId: string }
  | { type: 'permission.requested', sessionId: string, sequence?: number, appRequestId: string, request: RequestPermissionRequest }
  | { type: 'permission.resolved', sessionId: string, sequence?: number, appRequestId: string, response: RequestPermissionResponse }
  | { type: 'prompt.started', sessionId: string, sequence?: number, turnId: string, messageId: string, message?: string, attachments?: AcpAttachmentPart[] }
  | { type: 'prompt.completed', sessionId: string, sequence?: number, turnId: string, messageId: string, userMessageId?: string, completedAt?: string, response: PromptResponse }
  | { type: 'prompt.failed', sessionId: string, sequence?: number, turnId: string, messageId: string, error: string }
  | { type: 'prompt.cancelled', sessionId: string, sequence?: number, turnId?: string, messageId?: string }
