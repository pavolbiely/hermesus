import type { AcpListSessionsResponse } from '../types/acp-api'
import type { ChatSessionSummary } from '../types/chat'

export function acpSidebarSessions(response: AcpListSessionsResponse | null | undefined): ChatSessionSummary[] {
  return (response?.sessions || [])
    .map((session): ChatSessionSummary | null => {
      const id = session.sessionId
      if (!id) return null

      const metadata = session.appMetadata
      const title = metadata?.title?.trim() || session.title?.trim() || null
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
        messageCount: 0,
        createdAt: updatedAt,
        updatedAt
      } satisfies ChatSessionSummary
    })
    .filter((session): session is ChatSessionSummary => Boolean(session))
}
