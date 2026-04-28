import type { SessionDetailResponse } from '~/types/web-chat'

type HermesApi = ReturnType<typeof useHermesApi>

const inflightSessionRequests = new Map<string, Promise<SessionDetailResponse>>()

export function useWebChatSessionCache(api: HermesApi = useHermesApi()) {
  const sessions = useState<Record<string, SessionDetailResponse>>('web-chat-session-detail-cache', () => ({}))

  function get(sessionId: string) {
    return sessions.value[sessionId] || null
  }

  function set(response: SessionDetailResponse | null | undefined) {
    const sessionId = response?.session?.id
    if (!sessionId) return
    sessions.value = { ...sessions.value, [sessionId]: response }
  }

  function remove(sessionId: string) {
    const { [sessionId]: _removed, ...rest } = sessions.value
    sessions.value = rest
    inflightSessionRequests.delete(sessionId)
  }

  async function fetch(sessionId: string) {
    const existing = inflightSessionRequests.get(sessionId)
    if (existing) return await existing

    const request = api.getSession(sessionId)
      .then((response) => {
        set(response)
        return response
      })
      .finally(() => {
        inflightSessionRequests.delete(sessionId)
      })

    inflightSessionRequests.set(sessionId, request)
    return await request
  }

  function prefetch(sessionId: string) {
    if (get(sessionId) || inflightSessionRequests.has(sessionId)) return
    void fetch(sessionId).catch(() => {
      // Navigation will surface errors if the user actually opens the chat.
    })
  }

  return {
    sessions,
    get,
    set,
    remove,
    fetch,
    prefetch
  }
}
