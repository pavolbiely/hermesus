import type {
  ContentBlock,
  AvailableCommand,
  ForkSessionResponse,
  InitializeResponse,
  ListSessionsResponse,
  LoadSessionResponse,
  NewSessionResponse,
  PermissionOption,
  PromptResponse,
  RequestPermissionRequest,
  RequestPermissionResponse,
  SessionConfigOption,
  SessionModeState,
  SessionModelState,
  SessionNotification,
  SetSessionConfigOptionResponse,
  SetSessionModeResponse,
  SetSessionModelResponse
} from '@agentclientprotocol/sdk'

export type AcpBridgeHealth = {
  command: string
  args: string[]
  cwd: string
  initialized: boolean
  running: boolean
  pid?: number
  lastExit?: { code: number | null, signal: string | null }
  lastError?: string
  stderr: string[]
}

export type AcpInitializeApiResponse = {
  initialize: InitializeResponse
  health: AcpBridgeHealth
}

export type AcpPromptStartResponse = {
  sessionId: string
  turnId: string
  messageId: string
  status: 'started'
}

export type AcpCancelResponse = {
  sessionId: string
  status: 'cancelled'
}

export type AcpPromptRequest = {
  message?: string
  messageId?: string
  prompt?: ContentBlock[]
  turnId?: string
}

export type AcpSessionAppMetadata = {
  title?: string | null
  pinned?: boolean
  archived?: boolean
  workspace?: string | null
}

export type AcpSessionMetadataResponse = {
  sessionId: string
  metadata: AcpSessionAppMetadata
}

export type AcpListSessionsResponse = Omit<ListSessionsResponse, 'sessions'> & {
  sessions: Array<ListSessionsResponse['sessions'][number] & { appMetadata?: AcpSessionAppMetadata }>
}

export type AcpPermissionDecisionResponse = {
  appRequestId: string
  sessionId: string
  response: RequestPermissionResponse
}

export type AcpBridgeEvent =
  | { type: 'session.update', sessionId: string, sequence?: number, notification: SessionNotification, turnId?: string, messageId?: string }
  | { type: 'permission.requested', sessionId: string, sequence?: number, appRequestId: string, request: RequestPermissionRequest }
  | { type: 'permission.resolved', sessionId: string, sequence?: number, appRequestId: string, response: RequestPermissionResponse }
  | { type: 'prompt.started', sessionId: string, sequence?: number, turnId: string, messageId: string, message?: string }
  | { type: 'prompt.completed', sessionId: string, sequence?: number, turnId: string, messageId: string, response: PromptResponse }
  | { type: 'prompt.failed', sessionId: string, sequence?: number, turnId: string, messageId: string, error: string }
  | { type: 'prompt.cancelled', sessionId: string, sequence?: number }

export type AcpLoadSessionApiResponse = LoadSessionResponse & {
  events: AcpBridgeEvent[]
}

export type {
  ContentBlock,
  AvailableCommand,
  ForkSessionResponse,
  LoadSessionResponse,
  NewSessionResponse,
  PermissionOption,
  RequestPermissionRequest,
  RequestPermissionResponse,
  SessionConfigOption,
  SessionModeState,
  SessionModelState,
  SessionNotification,
  SetSessionConfigOptionResponse,
  SetSessionModeResponse,
  SetSessionModelResponse
}
