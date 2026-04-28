import type { WebChatSession } from '~/types/web-chat'

export function isSessionUnread(
  session: Pick<WebChatSession, 'id' | 'messageCount'>,
  readMessageCounts: Record<string, number>,
  readMessageCountsLoaded: boolean,
  hasLocalUnread = false
) {
  if (hasLocalUnread) return true
  if (!readMessageCountsLoaded) return false

  return Math.max(0, session.messageCount || 0) > Math.max(0, readMessageCounts[session.id] || 0)
}

export function readMessageCountForVisibleSession(
  session: Pick<WebChatSession, 'messageCount'> | undefined,
  observedMessageCount: number
) {
  return Math.max(0, observedMessageCount || 0, session?.messageCount || 0)
}

export function syncInitialReadMessageCounts(
  sessions: Pick<WebChatSession, 'id' | 'messageCount'>[],
  readMessageCounts: Record<string, number>,
  initialReadCount = (session: Pick<WebChatSession, 'id' | 'messageCount'>) => Math.max(0, session.messageCount || 0)
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
