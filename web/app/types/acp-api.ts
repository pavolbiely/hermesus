import type {
  ContentBlock,
  AvailableCommand,
  ForkSessionResponse,
  InitializeResponse,
  ListSessionsResponse,
  LoadSessionResponse,
  NewSessionResponse,
  PermissionOption,
  PlanEntry,
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
import type { AcpBridgeEvent, AcpChatMessage } from '../../shared/acp/types'

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
  sessions: Array<ListSessionsResponse['sessions'][number] & {
    appMetadata?: AcpSessionAppMetadata
    appLineage?: { rootSessionId: string, rootTitle: string | null }
    appActivePrompt?: { turnId: string, messageId: string } | null
  }>
}

export type AcpPermissionDecisionResponse = {
  appRequestId: string
  sessionId: string
  response: RequestPermissionResponse
}

export type AcpLoadSessionApiResponse = LoadSessionResponse & {
  events: AcpBridgeEvent[]
}

export type AcpPersistedPermission = {
  appRequestId: string
  request: RequestPermissionRequest
}

export type AcpPersistedPromptState = {
  status: 'running' | 'completed' | 'failed' | 'cancelled'
  turnId?: string
  messageId?: string
  userMessageId?: string
  error?: string
  startedAt?: string
  completedAt?: string
}

export type AcpTranscriptSnapshot = {
  sessionId: string
  cursor?: number
  updatedAt: string
  messages: AcpChatMessage[]
  pendingPermissions: AcpPersistedPermission[]
  planEntries: PlanEntry[]
  prompt: AcpPersistedPromptState | null
  models: SessionModelState | null
  modes: SessionModeState | null
  configOptions: SessionConfigOption[]
  availableCommands: AvailableCommand[]
}

export type AcpTranscriptApiResponse = {
  sessionId: string
  found: boolean
  transcript: AcpTranscriptSnapshot | null
  hasMore: boolean
  nextBefore: number | null
}

export type AcpTranscriptDeleteResponse = {
  sessionId: string
  deleted: boolean
}

export type AcpTranscriptClearResponse = {
  deleted: number
  cleared: boolean
}

export type AcpTranscriptRebuildResponse = {
  sessionId: string
  rebuilt: boolean
  events: AcpBridgeEvent[]
  transcript: AcpTranscriptSnapshot | null
}

export type {
  AcpBridgeEvent,
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
