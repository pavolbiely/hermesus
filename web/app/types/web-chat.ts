declare global {
  interface Window {
    __HERMES_SESSION_TOKEN__?: string
  }
}

export type InteractivePromptChoice = {
  id: string
  label: string
  description?: string | null
  style?: 'neutral' | 'primary' | 'warning' | 'error'
}

export type InteractivePrompt = {
  id: string
  runId: string
  sessionId: string
  kind: 'approval' | 'question'
  title: string
  description?: string | null
  detail?: string | null
  detailType: 'text' | 'command' | 'json'
  choices: InteractivePromptChoice[]
  freeText: boolean
  status: 'pending' | 'answered' | 'expired' | 'cancelled'
  selectedChoice?: string | null
  responseText?: string | null
  createdAt: string
  answeredAt?: string | null
  expiresAt?: string | null
}

export type RespondRunPromptRequest = {
  choice?: string | null
  text?: string | null
}

export type RespondRunPromptResponse = {
  prompt: InteractivePrompt
}

export type SteerRunRequest = {
  text: string
}

export type SteerRunResponse = {
  runId: string
  sessionId: string
  accepted: boolean
  messageId?: string | null
}

export type WebChatPart = {
  type: 'text' | 'reasoning' | 'tool' | 'media' | 'interactive_prompt' | 'changes' | 'steer'
  text?: string | null
  name?: string | null
  status?: string | null
  input?: unknown
  output?: unknown
  url?: string | null
  mediaType?: string | null
  approvalId?: string | null
  prompt?: InteractivePrompt | null
  changes?: WebChatWorkspaceChanges | null
  attachments?: WebChatAttachment[] | null
}

export type WebChatMessage = {
  id: string
  clientMessageId?: string | null
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

export type WebChatCommand = {
  id: string
  name: string
  description: string
  usage: string
  safety: 'safe' | 'confirmation_required' | 'blocked'
  requiresWorkspace: boolean
  requiresSession: boolean
}

export type WebChatCommandsResponse = {
  commands: WebChatCommand[]
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

export type ActiveRunSummary = {
  runId: string
  sessionId: string
  status: 'running' | 'stopping' | 'completed' | 'stopped' | 'failed'
  prompts: InteractivePrompt[]
}

export type SessionDetailResponse = {
  session: WebChatSession
  messages: WebChatMessage[]
  activeRun?: ActiveRunSummary | null
}

export type ExecuteCommandRequest = {
  command: string
  sessionId?: string
  workspace?: string | null
  model?: string | null
  reasoningEffort?: string | null
}

export type ExecuteCommandResponse = {
  commandId: string
  handled: boolean
  sessionId?: string | null
  message?: WebChatMessage | null
  changes?: WebChatWorkspaceChanges | null
}

export type StartRunResponse = {
  sessionId: string
  runId: string
  userMessageId?: string | null
}

export type DeleteSessionResponse = {
  ok: boolean
}

export {}
