export type ChatSessionSource = 'acp' | string | null

export type SlashCommand = {
  id: string
  name: string
  description?: string
  usage?: string
  safety?: 'safe' | 'confirm' | string
}

export type ChatPromptAttachment = {
  id: string
  name: string
  type: string
  size: number
  data: string
}

export type AppWorkspace = {
  id: string
  label: string
  path: string
  active: boolean
}

export type AppWorkspacesResponse = {
  workspaces: AppWorkspace[]
  activeWorkspace: string | null
}

export type HermesProfile = {
  id: string
  label: string
  active: boolean
}

export type HermesProfilesResponse = {
  profiles: HermesProfile[]
  activeProfile: string | null
}

export type AppWorkspaceResponse = {
  workspace: AppWorkspace
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

export type DeleteResponse = {
  deleted: boolean
}

export type FilePreviewRequest = {
  path: string
  workspace?: string | null
}

export type FilePreviewResolveRequest = {
  paths: string[]
  workspace?: string | null
}

export type AppFilePreviewReference = {
  path: string
  requestedPath: string
  relativePath?: string | null
  name: string
  mediaType: string
  size: number
  language?: string | null
  exists: boolean
}

export type FilePreviewResolveResponse = {
  files: AppFilePreviewReference[]
}

export type AppFilePreview = AppFilePreviewReference & {
  content?: string | null
  truncated: boolean
  previewable: boolean
  reason?: string | null
}

export type ChatSessionSummary = {
  id: string
  title: string | null
  preview: string
  source: ChatSessionSource
  model: string | null
  provider: string | null
  reasoningEffort: string | null
  workspace: string | null
  pinned: boolean
  archived: boolean
  running: boolean
  messageCount: number
  createdAt: string
  updatedAt: string
}
