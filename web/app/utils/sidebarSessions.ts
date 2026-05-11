import type { SessionGroup } from '~/utils/sessionGroups'
import type { ChatSessionSummary } from '~/types/chat'

export const MAX_COLLAPSED_SESSION_COUNT = 5

export function sessionTitle(session: ChatSessionSummary) {
  return session.title || session.preview || 'Untitled chat'
}

export function sessionTimestampTitle(updatedAt: string) {
  const timestamp = new Date(updatedAt).getTime()
  return Number.isFinite(timestamp) ? new Date(timestamp).toLocaleString() : undefined
}

export function sortedGroupSessions(group: SessionGroup, isUnreadSession: (session: ChatSessionSummary) => boolean) {
  return [...group.sessions].sort((a, b) => {
    return Number(b.pinned) - Number(a.pinned)
      || Number(isUnreadSession(b)) - Number(isUnreadSession(a))
  })
}

export function displayedGroupSessions(
  group: SessionGroup,
  expanded: boolean,
  isUnreadSession: (session: ChatSessionSummary) => boolean
) {
  const sessions = sortedGroupSessions(group, isUnreadSession)
  return expanded ? sessions : sessions.slice(0, MAX_COLLAPSED_SESSION_COUNT)
}

export function hiddenGroupSessionCount(group: SessionGroup, expanded: boolean) {
  if (expanded) return 0
  return Math.max(0, group.sessions.length - MAX_COLLAPSED_SESSION_COUNT)
}
