import type {
  DirectorySuggestionsResponse,
  ExecuteCommandRequest,
  ExecuteCommandResponse,
  FilePreviewRequest,
  FilePreviewResolveRequest,
  GenerateCommitMessageRequest,
  GitStatusResponse,
  CommitMessageSuggestion,
  ReorderWorkspacesRequest,
  SaveWorkspaceRequest,
  SessionDetailResponse,
  SessionListResponse,
  StartRunResponse,
  SteerRunRequest,
  SteerRunResponse,
  DeleteSessionResponse,
  RespondRunPromptRequest,
  RespondRunPromptResponse,
  UploadAttachmentsResponse,
  WebChatCapabilitiesResponse,
  WebChatCommandsResponse,
  WebChatFilePreview,
  WebChatFilePreviewReference,
  WebChatProfilesResponse,
  WebChatProviderUsageResponse,
  WebChatAppUpdateStatusResponse,
  WebChatUpdateStatusResponse,
  SwitchProfileResponse,
  WebChatWorkspaceResponse,
  WebChatWorkspacesResponse,
  WebChatWorkspaceChanges
} from '~/types/web-chat'

function hermesToken() {
  if (import.meta.server) return undefined
  const runtimeToken = useRuntimeConfig().public.hermesSessionToken
  return window.__HERMES_SESSION_TOKEN__ || (typeof runtimeToken === 'string' ? runtimeToken : undefined)
}

type ListSessionsOptions = {
  includeArchived?: boolean
}

type SessionDetailOptions = {
  includeWorkspaceChanges?: boolean
  messageLimit?: number
  messageBefore?: string
}

function sessionDetailQuery(options: SessionDetailOptions = {}) {
  return {
    includeWorkspaceChanges: options.includeWorkspaceChanges ?? true,
    messageLimit: options.messageLimit,
    messageBefore: options.messageBefore
  }
}

export function useHermesApi() {
  function authHeaders(headers?: HeadersInit) {
    const next = new Headers(headers)
    const token = hermesToken()
    if (token) next.set('X-Hermes-Session-Token', token)
    return next
  }

  async function request<T>(path: string, options: Parameters<typeof $fetch<T>>[1] = {}) {
    return await $fetch<T>(path, {
      ...options,
      headers: authHeaders(options.headers as HeadersInit | undefined)
    })
  }

  async function fetchBlob(path: string) {
    const response = await fetch(path, { headers: authHeaders() })
    if (!response.ok) {
      const message = response.status === 404 ? 'Attachment file not found' : `Request failed with ${response.status}`
      throw new Error(message)
    }
    return await response.blob()
  }

  return {
    getCapabilities: () => request<WebChatCapabilitiesResponse>('/api/web-chat/capabilities'),
    getProviderUsage: (provider?: string | null, model?: string | null) => request<WebChatProviderUsageResponse>('/api/web-chat/provider-usage', {
      query: {
        provider: provider || undefined,
        model: model || undefined
      }
    }),
    getUpdateStatus: () => request<WebChatUpdateStatusResponse>('/api/web-chat/update'),
    updateHermes: () => request<WebChatUpdateStatusResponse>('/api/web-chat/update', { method: 'POST' }),
    getAppUpdateStatus: () => request<WebChatAppUpdateStatusResponse>('/api/web-chat/app-update'),
    updateApp: () => request<WebChatAppUpdateStatusResponse>('/api/web-chat/app-update', { method: 'POST' }),
    getCommands: () => request<WebChatCommandsResponse>('/api/web-chat/commands'),
    executeCommand: (payload: ExecuteCommandRequest) => request<ExecuteCommandResponse>('/api/web-chat/commands/execute', {
      method: 'POST',
      body: payload
    }),
    getProfiles: () => request<WebChatProfilesResponse>('/api/web-chat/profiles'),
    switchProfile: (profile: string) => request<SwitchProfileResponse>('/api/web-chat/profiles/active', {
      method: 'POST',
      body: { profile }
    }),
    getWorkspaces: () => request<WebChatWorkspacesResponse>('/api/web-chat/workspaces'),
    getWorkspaceDirectories: (prefix: string) => request<DirectorySuggestionsResponse>('/api/web-chat/workspace-directories', {
      query: { prefix }
    }),
    createWorkspace: (payload: SaveWorkspaceRequest) => request<WebChatWorkspaceResponse>('/api/web-chat/workspaces', {
      method: 'POST',
      body: payload
    }),
    updateWorkspace: (id: string, payload: SaveWorkspaceRequest) => request<WebChatWorkspaceResponse>(`/api/web-chat/workspaces/${id}`, {
      method: 'PATCH',
      body: payload
    }),
    reorderWorkspaces: (payload: ReorderWorkspacesRequest) => request<WebChatWorkspacesResponse>('/api/web-chat/workspaces/order', {
      method: 'PATCH',
      body: payload
    }),
    deleteWorkspace: (id: string) => request<DeleteSessionResponse>(`/api/web-chat/workspaces/${id}`, {
      method: 'DELETE'
    }),
    getWorkspaceChanges: (workspace?: string | null) => request<WebChatWorkspaceChanges>('/api/web-chat/workspace-changes', {
      query: workspace ? { workspace } : undefined
    }),
    getGitStatus: (workspace?: string | null) => request<GitStatusResponse>('/api/web-chat/git/status', {
      query: workspace ? { workspace } : undefined
    }),
    generateCommitMessage: (payload: GenerateCommitMessageRequest) => request<CommitMessageSuggestion>('/api/web-chat/git/commit-message', {
      method: 'POST',
      body: payload
    }),
    fetchFilePreview: (payload: FilePreviewRequest) => request<WebChatFilePreview>('/api/web-chat/file-preview', {
      method: 'POST',
      body: payload
    }),
    resolveFilePreviewPaths: (payload: FilePreviewResolveRequest) => request<WebChatFilePreviewReference[]>('/api/web-chat/file-preview/resolve', {
      method: 'POST',
      body: payload
    }),
    listSessions: (options: ListSessionsOptions = {}) => request<SessionListResponse>('/api/web-chat/sessions', {
      query: {
        includeArchived: options.includeArchived || undefined
      }
    }),
    getSession: (id: string, options?: SessionDetailOptions) => request<SessionDetailResponse>(`/api/web-chat/sessions/${id}`, {
      query: sessionDetailQuery(options)
    }),
    renameSession: (id: string, title: string) => request<SessionDetailResponse>(`/api/web-chat/sessions/${id}`, {
      method: 'PATCH',
      body: { title }
    }),
    setSessionArchived: (id: string, archived: boolean) => request<SessionDetailResponse>(`/api/web-chat/sessions/${id}`, {
      method: 'PATCH',
      body: { archived }
    }),
    setSessionPinned: (id: string, pinned: boolean) => request<SessionDetailResponse>(`/api/web-chat/sessions/${id}`, {
      method: 'PATCH',
      body: { pinned }
    }),
    editMessage: (sessionId: string, messageId: string, content: string) => request<SessionDetailResponse>(`/api/web-chat/sessions/${sessionId}/messages/${messageId}`, {
      method: 'PATCH',
      body: { content }
    }),
    deleteSession: (id: string) => request<DeleteSessionResponse>(`/api/web-chat/sessions/${id}`, {
      method: 'DELETE'
    }),
    duplicateSession: (id: string) => request<SessionDetailResponse>(`/api/web-chat/sessions/${id}/duplicate`, {
      method: 'POST'
    }),
    createSession: (message: string) => request<SessionDetailResponse>('/api/web-chat/sessions', {
      method: 'POST',
      body: { message }
    }),
    startRun: (
      input: string,
      options: {
        sessionId?: string
        model?: string | null
        provider?: string | null
        reasoningEffort?: string | null
        workspace?: string | null
        profile?: string | null
        attachments?: string[]
        editedMessageId?: string
        clientMessageId?: string
      } = {}
    ) => request<StartRunResponse>('/api/web-chat/runs', {
      method: 'POST',
      body: {
        input,
        clientMessageId: options.clientMessageId,
        sessionId: options.sessionId,
        model: options.model,
        provider: options.provider,
        reasoningEffort: options.reasoningEffort,
        workspace: options.workspace,
        profile: options.profile,
        attachments: options.attachments,
        editedMessageId: options.editedMessageId
      }
    }),
    respondRunPrompt: (runId: string, promptId: string, payload: RespondRunPromptRequest) =>
      request<RespondRunPromptResponse>(`/api/web-chat/runs/${runId}/prompts/${promptId}/response`, {
        method: 'POST',
        body: payload
      }),
    steerRun: (runId: string, payload: SteerRunRequest) =>
      request<SteerRunResponse>(`/api/web-chat/runs/${runId}/steer`, {
        method: 'POST',
        body: payload
      }),
    uploadAttachments: (files: File[], workspace?: string | null) => {
      const body = new FormData()
      for (const file of files) body.append('files', file)
      if (workspace) body.append('workspace', workspace)
      return request<UploadAttachmentsResponse>('/api/web-chat/attachments', { method: 'POST', body })
    },
    fetchAttachmentContent: (attachment: { id: string, workspace?: string | null } | string) => {
      const id = typeof attachment === 'string' ? attachment : attachment.id
      const workspace = typeof attachment === 'string' ? null : attachment.workspace
      const query = workspace ? `?workspace=${encodeURIComponent(workspace)}` : ''
      return fetchBlob(`/api/web-chat/attachments/${id}/content${query}`)
    }
  }
}
