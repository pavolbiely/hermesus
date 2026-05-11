import type { ChatSessionSummary } from '~/types/chat'

type SessionReadState = Pick<ChatSessionSummary, 'id' | 'messageCount'>

export function isSessionUnread(
  session: SessionReadState,
  readMessageCounts: Record<string, number>,
  readMessageCountsLoaded: boolean,
  hasLocalUnread = false
) {
  if (hasLocalUnread) return true
  if (!readMessageCountsLoaded) return false

  return Math.max(0, session.messageCount || 0) > Math.max(0, readMessageCounts[session.id] || 0)
}

export function readMessageCountForVisibleSession(
  session: Pick<ChatSessionSummary, 'messageCount'> | undefined,
  observedMessageCount: number
) {
  return Math.max(0, observedMessageCount || 0, session?.messageCount || 0)
}

export function syncInitialReadMessageCounts(
  sessions: SessionReadState[],
  readMessageCounts: Record<string, number>,
  initialReadCount = (session: SessionReadState) => Math.max(0, session.messageCount || 0)
) {
  let changed = false
  const next = { ...readMessageCounts }
  const sessionIds = new Set(sessions.map(session => session.id))

  for (const session of sessions) {
    if (next[session.id] === undefined) {
      next[session.id] = Math.max(0, initialReadCount(session) || 0)
      changed = true
    }
  }

  for (const id of Object.keys(next)) {
    if (!sessionIds.has(id)) {
      delete next[id]
      changed = true
    }
  }

  return changed ? next : readMessageCounts
}
