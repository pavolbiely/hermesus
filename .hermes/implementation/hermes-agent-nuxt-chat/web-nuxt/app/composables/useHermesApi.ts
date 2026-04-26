import type { SessionDetailResponse, SessionListResponse, StartRunResponse } from '~/types/web-chat'

function hermesToken() {
  if (import.meta.server) return undefined
  return window.__HERMES_SESSION_TOKEN__
}

export function useHermesApi() {
  async function request<T>(path: string, options: Parameters<typeof $fetch<T>>[1] = {}) {
    return await $fetch<T>(path, {
      ...options,
      headers: {
        ...(options.headers || {}),
        ...(hermesToken() ? { 'X-Hermes-Session-Token': hermesToken() } : {})
      }
    })
  }

  return {
    listSessions: () => request<SessionListResponse>('/api/web-chat/sessions'),
    getSession: (id: string) => request<SessionDetailResponse>(`/api/web-chat/sessions/${id}`),
    createSession: (message: string) => request<SessionDetailResponse>('/api/web-chat/sessions', {
      method: 'POST',
      body: { message }
    }),
    startRun: (input: string, sessionId?: string) => request<StartRunResponse>('/api/web-chat/runs', {
      method: 'POST',
      body: { input, sessionId }
    })
  }
}
