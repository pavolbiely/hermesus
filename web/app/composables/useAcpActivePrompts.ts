export function useAcpActivePrompts() {
  const runningPromptTurns = useState<Record<string, string>>('acp-active-prompt-turns', () => ({}))

  function markRunning(sessionId: string, turnId: string) {
    if (!sessionId || !turnId) return
    runningPromptTurns.value = { ...runningPromptTurns.value, [sessionId]: turnId }
  }

  function markFinished(sessionId: string, turnId?: string | null) {
    const activeTurnId = runningPromptTurns.value[sessionId]
    if (!activeTurnId || (turnId && activeTurnId !== turnId)) return

    const next = { ...runningPromptTurns.value }
    delete next[sessionId]
    runningPromptTurns.value = next
  }

  function isRunning(sessionId: string) {
    return Boolean(runningPromptTurns.value[sessionId])
  }

  return {
    runningPromptTurns,
    markRunning,
    markFinished,
    isRunning
  }
}
