import type {
  AcpBridgeEvent,
  AcpBridgeHealth,
  AcpCancelResponse,
  AcpInitializeApiResponse,
  AcpListSessionsResponse,
  AcpLoadSessionApiResponse,
  AcpPermissionDecisionResponse,
  AcpPromptRequest,
  AcpPromptStartResponse,
  AcpSessionAppMetadata,
  AcpSessionMetadataResponse,
  ForkSessionResponse,
  NewSessionResponse,
  SetSessionConfigOptionResponse,
  SetSessionModeResponse,
  SetSessionModelResponse
} from '~/types/acp-api'

function acpSessionEventsUrl(sessionId: string, options: { afterSequence?: number, replay?: boolean } = {}) {
  const params = new URLSearchParams()
  if (options.afterSequence !== undefined) params.set('after', String(options.afterSequence))
  if (options.replay === false) params.set('replay', 'false')
  const query = params.toString()
  return `/api/acp/sessions/${encodeURIComponent(sessionId)}/events${query ? `?${query}` : ''}`
}

export function useAcpApi() {
  async function request<T>(path: string, options: Parameters<typeof $fetch<T>>[1] = {}) {
    return await $fetch<T>(path, options)
  }

  function subscribeSession(
    sessionId: string,
    onEvent: (event: AcpBridgeEvent) => void,
    onError?: (event: Event) => void,
    options: { afterSequence?: number, replay?: boolean } = {}
  ) {
    const source = new EventSource(acpSessionEventsUrl(sessionId, options))
    const eventTypes: AcpBridgeEvent['type'][] = [
      'session.update',
      'transcript.truncated',
      'permission.requested',
      'permission.resolved',
      'prompt.started',
      'prompt.completed',
      'prompt.failed',
      'prompt.cancelled'
    ]

    eventTypes.forEach((type) => {
      source.addEventListener(type, (event) => {
        onEvent(JSON.parse((event as MessageEvent).data) as AcpBridgeEvent)
      })
    })

    if (onError) source.addEventListener('error', onError)
    return source
  }

  return {
    health: () => request<AcpBridgeHealth>('/api/acp/health'),
    initialize: () => request<AcpInitializeApiResponse>('/api/acp/initialize', { method: 'POST' }),
    listSessions: () => request<AcpListSessionsResponse>('/api/acp/sessions'),
    createSession: (payload: Record<string, unknown> = {}) => request<NewSessionResponse>('/api/acp/sessions', { method: 'POST', body: payload }),
    loadSession: (sessionId: string, options: { signal?: AbortSignal } = {}) => request<AcpLoadSessionApiResponse>(`/api/acp/sessions/${encodeURIComponent(sessionId)}`, {
      signal: options.signal
    }),
    updateSessionMetadata: (sessionId: string, patch: Partial<AcpSessionAppMetadata>) => request<AcpSessionMetadataResponse>(`/api/acp/sessions/${encodeURIComponent(sessionId)}/metadata`, {
      method: 'PATCH',
      body: patch
    }),
    setSessionMode: (sessionId: string, modeId: string) => request<SetSessionModeResponse>(`/api/acp/sessions/${encodeURIComponent(sessionId)}/mode`, {
      method: 'POST',
      body: { modeId }
    }),
    setSessionModel: (sessionId: string, modelId: string) => request<SetSessionModelResponse>(`/api/acp/sessions/${encodeURIComponent(sessionId)}/model`, {
      method: 'POST',
      body: { modelId }
    }),
    setSessionConfigOption: (sessionId: string, configId: string, payload: { type?: 'boolean', value: boolean | string }) => request<SetSessionConfigOptionResponse>(`/api/acp/sessions/${encodeURIComponent(sessionId)}/config-options/${encodeURIComponent(configId)}`, {
      method: 'POST',
      body: payload
    }),
    respondToPermission: (appRequestId: string, payload: { optionId?: string, cancelled?: boolean }) => request<AcpPermissionDecisionResponse>(`/api/acp/permissions/${encodeURIComponent(appRequestId)}`, {
      method: 'POST',
      body: payload
    }),
    forkSession: (sessionId: string) => request<ForkSessionResponse>(`/api/acp/sessions/${encodeURIComponent(sessionId)}/fork`, { method: 'POST' }),
    closeSession: (sessionId: string) => request<{ sessionId: string, closed: boolean }>(`/api/acp/sessions/${encodeURIComponent(sessionId)}/close`, { method: 'POST' }),
    startPrompt: (sessionId: string, payload: AcpPromptRequest) => request<AcpPromptStartResponse>(`/api/acp/sessions/${encodeURIComponent(sessionId)}/prompts`, {
      method: 'POST',
      body: payload
    }),
    prompt: (sessionId: string, message: string) => request<AcpPromptStartResponse>(`/api/acp/sessions/${encodeURIComponent(sessionId)}/prompts`, {
      method: 'POST',
      body: { message }
    }),
    cancelPrompt: (sessionId: string) => request<AcpCancelResponse>(`/api/acp/sessions/${encodeURIComponent(sessionId)}/cancel`, { method: 'POST' }),
    cancel: (sessionId: string) => request<AcpCancelResponse>(`/api/acp/sessions/${encodeURIComponent(sessionId)}/cancel`, { method: 'POST' }),
    subscribeSession
  }
}
