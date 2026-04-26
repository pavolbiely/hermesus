declare global {
  interface Window {
    __HERMES_SESSION_TOKEN__?: string
  }
}

export type WebChatPart = {
  type: 'text' | 'reasoning' | 'tool' | 'media' | 'approval'
  text?: string | null
  name?: string | null
  status?: string | null
  input?: unknown
  output?: unknown
  url?: string | null
  mediaType?: string | null
  approvalId?: string | null
}

export type WebChatMessage = {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  parts: WebChatPart[]
  createdAt: string
  reasoning?: string | null
  toolName?: string | null
  toolCalls?: unknown
}

export type WebChatSession = {
  id: string
  title: string | null
  preview: string
  source: string | null
  model: string | null
  messageCount: number
  createdAt: string
  updatedAt: string
}

export type SessionListResponse = {
  sessions: WebChatSession[]
}

export type SessionDetailResponse = {
  session: WebChatSession
  messages: WebChatMessage[]
}

export type StartRunResponse = {
  sessionId: string
  runId: string
}

export {}
