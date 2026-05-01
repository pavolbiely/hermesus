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

export type AgentStatusEvent = {
  kind: 'lifecycle' | 'warn' | string
  message: string
  messageId?: string | null
  createdAt?: string | null
}

export type WebChatSystemEventType =
  | 'run_stopped'
  | 'run_failed'
  | 'run_steered'
  | 'prompt_expired'
  | 'prompt_cancelled'
  | 'agent_warning'

export type WebChatSystemEventSeverity = 'info' | 'warning' | 'error'

export type WebChatTaskPlanItemStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled'

export type WebChatTaskPlanItem = {
  id: string
  content: string
  status: WebChatTaskPlanItemStatus
}

export type WebChatTaskPlan = {
  items: WebChatTaskPlanItem[]
  updatedAt?: string | null
}

export type WebChatRunEta = {
  remainingMs: number
  estimatedCompletionAt: string
  confidence: 'low' | 'medium' | 'high'
  basis: 'default' | 'profile' | 'workspace' | 'workspace_model' | 'task_type' | 'project_area' | 'validation_profile' | 'observed'
  taskType?: string | null
  projectArea?: string | null
  validationProfile?: string | null
  totalSlices?: number | null
  completedSlices?: number | null
  sliceMs?: number | null
  updatedAt: string
}

export type WebChatPart = {
  type: 'text' | 'reasoning' | 'tool' | 'media' | 'interactive_prompt' | 'changes' | 'steer' | 'status' | 'event' | 'task_plan'
  text?: string | null
  name?: string | null
  status?: string | null
  eventType?: WebChatSystemEventType | string | null
  severity?: WebChatSystemEventSeverity | string | null
  title?: string | null
  description?: string | null
  occurredAt?: string | null
  startedAt?: string | null
  completedAt?: string | null
  durationMs?: number | null
  input?: unknown
  output?: unknown
  url?: string | null
  mediaType?: string | null
  approvalId?: string | null
  prompt?: InteractivePrompt | null
  taskPlan?: WebChatTaskPlan | null
  changes?: WebChatWorkspaceChanges | null
  attachments?: WebChatAttachment[] | null
  metadata?: Record<string, unknown> | null
}

export type WebChatMessage = {
  id: string
  clientMessageId?: string | null
  localStatus?: 'sending' | 'failed' | null
  localError?: string | null
  role: 'user' | 'assistant' | 'system' | 'tool'
  parts: WebChatPart[]
  createdAt: string
  tokenCount?: number | null
  inputTokens?: number | null
  outputTokens?: number | null
  cacheReadTokens?: number | null
  cacheWriteTokens?: number | null
  reasoningTokens?: number | null
  contextTokens?: number | null
  apiCalls?: number | null
  generationDurationMs?: number | null
  modelDurationMs?: number | null
  toolDurationMs?: number | null
  promptWaitDurationMs?: number | null
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
  provider: string | null
  reasoningEffort: string | null
  workspace: string | null
  pinned: boolean
  messageCount: number
  createdAt: string
  updatedAt: string
}

export type WebChatModelCapability = {
  id: string
  label: string
  reasoningEfforts: string[]
  defaultReasoningEffort: string | null
  contextWindowTokens?: number | null
  autoCompressTokens?: number | null
  provider?: string | null
  providerLabel?: string | null
}

export type WebChatCapabilitiesResponse = {
  provider: string
  defaultModel: string | null
  defaultProvider?: string | null
  models: WebChatModelCapability[]
}

export type WebChatProviderUsageWindow = {
  label: string
  usedPercent: number
  remainingPercent: number
  windowMinutes?: number | null
  resetsAt?: string | null
}

export type WebChatProviderUsageLimit = {
  id: string
  label: string
  windows: WebChatProviderUsageWindow[]
}

export type WebChatProviderUsageResponse = {
  provider: string
  model?: string | null
  source: string
  available: boolean
  unavailableReason?: string | null
  limits: WebChatProviderUsageLimit[]
  capturedAt?: string | null
}

export type WebChatUpdateStatusResponse = {
  updateAvailable: boolean
  runtimeOutOfSync: boolean
  upstreamPath: string
  runtimePath: string
  branch: string
  currentRevision?: string | null
  remoteRevision?: string | null
  runtimeRevision?: string | null
}

export type WebChatAppUpdateStatusResponse = {
  updateAvailable: boolean
  appPath: string
  branch: string
  currentRevision?: string | null
  remoteRevision?: string | null
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

export type ReorderWorkspacesRequest = {
  workspaceIds: string[]
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

export type FilePreviewRequest = {
  path: string
  workspace?: string | null
}

export type FilePreviewResolveRequest = {
  paths: string[]
  workspace?: string | null
}

export type WebChatFilePreviewReference = {
  path: string
  requestedPath: string
  relativePath?: string | null
  name: string
  mediaType: string
  size: number
  language?: string | null
  exists: boolean
}

export type WebChatFilePreview = {
  path: string
  requestedPath: string
  relativePath?: string | null
  name: string
  mediaType: string
  size: number
  language?: string | null
  content?: string | null
  truncated: boolean
  previewable: boolean
  reason?: string | null
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

export type WebChatIsolatedWorkspace = {
  sessionId: string
  sourceWorkspace: string
  sourceGitRoot: string
  worktreePath: string
  branchName: string
  baseRef: string
  status: 'active' | 'applied' | 'deleted' | 'missing' | 'cleaned'
  dirty: boolean
}

export type SessionListResponse = {
  sessions: WebChatSession[]
}

export type ActiveRunSummary = {
  runId: string
  sessionId: string
  status: 'running' | 'stopping' | 'completed' | 'stopped' | 'failed'
  prompts: InteractivePrompt[]
  eta?: WebChatRunEta | null
}

export type SessionDetailResponse = {
  session: WebChatSession
  messages: WebChatMessage[]
  activeRun?: ActiveRunSummary | null
  isolatedWorkspace?: WebChatIsolatedWorkspace | null
  compressionCount?: number
  messagesHasMoreBefore?: boolean
  messagesTotal?: number | null
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


export type GitChangeArea = 'staged' | 'unstaged' | 'untracked'
export type GitChangeStatus = 'created' | 'edited' | 'deleted' | 'renamed' | 'copied' | 'untracked'

export type GitFileSelection = {
  path: string
  area: GitChangeArea
}

export type GitStatusFile = {
  path: string
  oldPath?: string | null
  area: GitChangeArea
  status: GitChangeStatus
  staged: boolean
  unstaged: boolean
  untracked: boolean
  additions?: number | null
  deletions?: number | null
  binary?: boolean
}

export type GitStatusResponse = {
  workspace: string
  root: string
  head?: string | null
  branch?: string | null
  ahead?: number | null
  behind?: number | null
  files: GitStatusFile[]
  hasStagedChanges: boolean
  hasUnstagedChanges: boolean
  hasUntrackedChanges: boolean
}

export type GenerateCommitMessageRequest = {
  workspace?: string | null
  sessionId?: string | null
  chatContext?: string | null
  selection: GitFileSelection[]
}

export type CommitMessageSuggestion = {
  subject: string
  body?: string | null
  warnings: string[]
  splitSuggestions: Array<{
    subject: string
    paths: string[]
    reason: string
  }>
  rulesSource: string
  contextSummary: string
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
