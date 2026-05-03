type HeaderSession = {
  title?: string | null
  preview?: string | null
}

type ChatHeaderTitleInput = {
  isLoadingSession: boolean
  sessionError: unknown
  hasSession: boolean
  session?: HeaderSession | null
  titleOverride?: string | null
}

export function resolveChatHeaderTitle({
  isLoadingSession,
  sessionError,
  hasSession,
  session,
  titleOverride
}: ChatHeaderTitleInput) {
  if (isLoadingSession) return 'Loading chat…'
  if (sessionError || !hasSession) return 'Chat unavailable'

  const override = titleOverride?.trim()
  if (override) return override

  return session?.title || session?.preview || 'Chat'
}
