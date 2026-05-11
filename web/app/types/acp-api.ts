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
import type { AcpBridgeEvent } from '../../shared/acp/types'

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
  replaceFromMessageId?: string
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
    appUpdatedAt?: string | null
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

export type {
  AcpBridgeEvent,
  ContentBlock,
  AvailableCommand,
  ForkSessionResponse,
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
}
