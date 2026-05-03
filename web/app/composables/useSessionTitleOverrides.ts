export function useSessionTitleOverrides() {
  const titles = useState<Record<string, string>>('web-chat-session-title-overrides', () => ({}))

  function get(sessionId: string | null | undefined) {
    if (!sessionId) return null
    return titles.value[sessionId] || null
  }

  function set(sessionId: string | null | undefined, title: string | null | undefined) {
    if (!sessionId) return

    const normalized = title?.trim()
    if (!normalized) {
      const { [sessionId]: _removed, ...rest } = titles.value
      titles.value = rest
      return
    }

    titles.value = { ...titles.value, [sessionId]: normalized }
  }

  return {
    titles,
    get,
    set
  }
}
