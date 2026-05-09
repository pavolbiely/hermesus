import type { SessionDetailResponse } from '~/types/web-chat'

type HermesApi = ReturnType<typeof useHermesApi>
type SessionDetailOptions = Parameters<HermesApi['getSession']>[1]

const inflightSessionRequests = new Map<string, Promise<SessionDetailResponse>>()
const sessionRequestGenerations = new Map<string, number>()

function requestKey(sessionId: string, options: SessionDetailOptions = {}) {
  return [sessionId, options.messageLimit || '', options.messageBefore || ''].join(':')
}

function requestGeneration(sessionId: string) {
  return sessionRequestGenerations.get(sessionId) || 0
}

function dropInflightSessionRequests(sessionId: string) {
  for (const key of Array.from(inflightSessionRequests.keys())) {
    if (key === sessionId || key.startsWith(`${sessionId}:`)) inflightSessionRequests.delete(key)
  }
}

function isCanonicalSessionRequest(options: SessionDetailOptions = {}) {
  return !options.messageBefore
}

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

  function update(sessionId: string, updater: (current: SessionDetailResponse) => SessionDetailResponse) {
    const current = get(sessionId)
    if (!current) return null

    const next = updater(current)
    sessions.value = { ...sessions.value, [sessionId]: next }
    return next
  }

  function remove(sessionId: string) {
    const { [sessionId]: _removed, ...rest } = sessions.value
    sessions.value = rest
    dropInflightSessionRequests(sessionId)
  }

  function invalidate(sessionId: string) {
    sessionRequestGenerations.set(sessionId, requestGeneration(sessionId) + 1)
    dropInflightSessionRequests(sessionId)
  }

  function generation(sessionId: string) {
    return requestGeneration(sessionId)
  }

  function isCurrentGeneration(sessionId: string, generation: number) {
    return requestGeneration(sessionId) === generation
  }

  async function fetch(sessionId: string, options: SessionDetailOptions = {}): Promise<SessionDetailResponse> {
    const key = requestKey(sessionId, options)
    const generation = requestGeneration(sessionId)
    const existing = inflightSessionRequests.get(key)
    if (existing) return await existing

    let request: Promise<SessionDetailResponse>
    request = api.getSession(sessionId, options)
      .then((response): Promise<SessionDetailResponse> | SessionDetailResponse => {
        if (requestGeneration(sessionId) !== generation && isCanonicalSessionRequest(options)) return fetch(sessionId, options)
        if (requestGeneration(sessionId) === generation && isCanonicalSessionRequest(options)) set(response)
        return response
      })
      .finally(() => {
        if (inflightSessionRequests.get(key) === request) inflightSessionRequests.delete(key)
      })

    inflightSessionRequests.set(key, request)
    return await request
  }

  function prefetch(sessionId: string, options: SessionDetailOptions = {}) {
    const key = requestKey(sessionId, options)
    if (get(sessionId) || inflightSessionRequests.has(key)) return
    void fetch(sessionId, options).catch(() => {
      // Navigation will surface errors if the user actually opens the chat.
    })
  }

  return {
    sessions,
    get,
    set,
    update,
    remove,
    invalidate,
    generation,
    isCurrentGeneration,
    fetch,
    prefetch
  }
}
