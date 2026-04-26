declare global {
  interface Window {
    __HERMES_SESSION_TOKEN__?: string
  }
}

export type WebChatPart = {
  type: 'text' | 'reasoning' | 'tool' | 'media' | 'approval' | 'changes'
  text?: string | null
  name?: string | null
  status?: string | null
  input?: unknown
  output?: unknown
  url?: string | null
  mediaType?: string | null
  approvalId?: string | null
  changes?: WebChatWorkspaceChanges | null
  attachments?: WebChatAttachment[] | null
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
  reasoningEffort: string | null
  workspace: string | null
  messageCount: number
  createdAt: string
  updatedAt: string
}

export type WebChatModelCapability = {
  id: string
  label: string
  reasoningEfforts: string[]
  defaultReasoningEffort: string | null
}

export type WebChatCapabilitiesResponse = {
  provider: string
  defaultModel: string | null
  models: WebChatModelCapability[]
}

export type WebChatProfile = {
  id: string
  label: string
  path: string
  active: boolean
}

export type WebChatProfilesResponse = {
  profiles: WebChatProfile[]
  activeProfile: string
}

export type SwitchProfileResponse = WebChatProfilesResponse & {
  restarting: boolean
}

export type WebChatWorkspace = {
  id: string
  label: string
  path: string
  active: boolean
}

export type WebChatWorkspacesResponse = {
  workspaces: WebChatWorkspace[]
  activeWorkspace: string | null
}

export type WebChatWorkspaceResponse = {
  workspace: WebChatWorkspace
}

export type SaveWorkspaceRequest = {
  label: string
  path: string
}

export type DirectorySuggestionsResponse = {
  suggestions: string[]
}

export type WebChatAttachment = {
  id: string
  name: string
  mediaType: string
  size: number
  path: string
  workspace?: string | null
  relativePath?: string | null
  url?: string | null
  exists?: boolean
}

export type UploadAttachmentsResponse = {
  attachments: WebChatAttachment[]
}

export type WebChatFileChange = {
  path: string
  status: 'created' | 'edited' | 'deleted' | 'renamed' | 'copied'
  additions: number
  deletions: number
}

export type WebChatPatch = {
  files: Array<{
    path: string
    oldPath?: string | null
    status: WebChatFileChange['status']
    patch: string | null
    truncated?: boolean
  }>
}

export type WebChatWorkspaceChanges = {
  files: WebChatFileChange[]
  totalFiles: number
  totalAdditions: number
  totalDeletions: number
  workspace?: string | null
  runId?: string | null
  capturedAt?: string | null
  patch?: WebChatPatch | null
  patchTruncated?: boolean | null
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

export type DeleteSessionResponse = {
  ok: boolean
}

export {}
