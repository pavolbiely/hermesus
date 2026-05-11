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
      const updatedAt = latestIsoTimestamp(session.appUpdatedAt, session.updatedAt) || new Date().toISOString()

      return {
        id,
        title,
        preview: title || 'ACP chat',
        source: 'acp',
        model: null,
        provider: null,
        reasoningEffort: null,
        workspace: metadata?.workspace || sessionWorkspace(session.cwd),
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

function sessionWorkspace(cwd: string | null | undefined) {
  const value = cwd?.trim()
  return value && (value.startsWith('/') || value === '~' || value.startsWith('~/')) ? value : null
}

function latestIsoTimestamp(...values: Array<string | null | undefined>) {
  return values.reduce<string | null>((latest, value) => {
    if (!value) return latest
    const time = Date.parse(value)
    if (!Number.isFinite(time)) return latest
    if (!latest || time > Date.parse(latest)) return value
    return latest
  }, null)
}
