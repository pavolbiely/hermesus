import type {
  DirectorySuggestionsResponse,
  ExecuteCommandRequest,
  ExecuteCommandResponse,
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
  WebChatProfilesResponse,
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
    deleteWorkspace: (id: string) => request<DeleteSessionResponse>(`/api/web-chat/workspaces/${id}`, {
      method: 'DELETE'
    }),
    getWorkspaceChanges: (workspace?: string | null) => request<WebChatWorkspaceChanges>('/api/web-chat/workspace-changes', {
      query: workspace ? { workspace } : undefined
    }),
    listSessions: () => request<SessionListResponse>('/api/web-chat/sessions'),
    getSession: (id: string) => request<SessionDetailResponse>(`/api/web-chat/sessions/${id}`, {
      query: { includeWorkspaceChanges: true }
    }),
    renameSession: (id: string, title: string) => request<SessionDetailResponse>(`/api/web-chat/sessions/${id}`, {
      method: 'PATCH',
      body: { title }
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
