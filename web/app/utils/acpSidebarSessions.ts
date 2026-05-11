import type { AcpListSessionsResponse } from '../types/acp-api'
import type { ChatSessionSummary } from '../types/chat'

export function acpSidebarSessions(response: AcpListSessionsResponse | null | undefined): ChatSessionSummary[] {
  const sourceSessionsById = new Map((response?.sessions || []).map(session => [session.sessionId, session]))
  const sessions = (response?.sessions || [])
    .map((session): ChatSessionSummary | null => {
      const id = session.sessionId
      if (!id) return null

      const metadata = session.appMetadata
      const rootTitle = session.appLineage?.rootTitle?.trim()
      const title = metadata?.title?.trim() || rootTitle || session.title?.trim() || null
      const updatedAt = session.updatedAt || new Date().toISOString()

      return {
        id,
        title,
        preview: title || 'ACP chat',
        source: 'acp',
        model: null,
        provider: null,
        reasoningEffort: null,
        workspace: metadata?.workspace || session.cwd || null,
        pinned: Boolean(metadata?.pinned),
        archived: Boolean(metadata?.archived),
        running: Boolean(session.appActivePrompt),
        messageCount: 0,
        createdAt: updatedAt,
        updatedAt
      } satisfies ChatSessionSummary
    })
    .filter((session): session is ChatSessionSummary => Boolean(session))

  const visibleSessionsByLineage = new Map<string, ChatSessionSummary>()
  for (const session of sessions) {
    const sourceSession = sourceSessionsById.get(session.id)
    const lineageId = sourceSession?.appLineage?.rootSessionId || session.id
    const current = visibleSessionsByLineage.get(lineageId)
    if (!current || Date.parse(session.updatedAt) >= Date.parse(current.updatedAt)) {
      visibleSessionsByLineage.set(lineageId, session)
    }
  }

  return Array.from(visibleSessionsByLineage.values())
}
