import type { WebChatSession } from '~/types/web-chat'

export function isSessionUnread(
  session: Pick<WebChatSession, 'id' | 'messageCount'>,
  readMessageCounts: Record<string, number>,
  readMessageCountsLoaded: boolean,
  hasPromptUnread = false
) {
  if (hasPromptUnread) return true
  if (!readMessageCountsLoaded) return false

  return Math.max(0, session.messageCount || 0) > Math.max(0, readMessageCounts[session.id] || 0)
}

export function syncInitialReadMessageCounts(
  sessions: Pick<WebChatSession, 'id' | 'messageCount'>[],
  readMessageCounts: Record<string, number>
) {
  let changed = false
  const next = { ...readMessageCounts }
  const sessionIds = new Set(sessions.map(session => session.id))

  for (const session of sessions) {
    if (next[session.id] === undefined) {
      next[session.id] = Math.max(0, session.messageCount || 0)
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
