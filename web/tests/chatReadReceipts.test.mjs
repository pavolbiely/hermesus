import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isSessionUnread, readMessageCountForVisibleSession, syncInitialReadMessageCounts } from '../app/utils/chatReadReceipts.ts'

test('does not mark active sessions read just because they are open', () => {
  assert.equal(isSessionUnread(
    { id: 'chat-1', messageCount: 4 },
    { 'chat-1': 3 },
    true,
    false
  ), true)
})

test('initial read-count sync only initializes unknown sessions and prunes deleted ones', () => {
  const current = { 'chat-1': 3, deleted: 7 }
  const next = syncInitialReadMessageCounts([
    { id: 'chat-1', messageCount: 5 },
    { id: 'chat-2', messageCount: 2 }
  ], current)

  assert.deepEqual(next, {
    'chat-1': 3,
    'chat-2': 2
  })
})

test('local unread keeps a session unread regardless of message count', () => {
  assert.equal(isSessionUnread(
    { id: 'chat-1', messageCount: 3 },
    { 'chat-1': 3 },
    true,
    true
  ), true)
})

test('new sessions can be initialized unread after the first sidebar sync', () => {
  const next = syncInitialReadMessageCounts(
    [
      { id: 'chat-1', messageCount: 5 },
      { id: 'chat-2', messageCount: 2 }
    ],
    { 'chat-1': 5 },
    session => session.id === 'chat-2' ? 0 : session.messageCount
  )

  assert.deepEqual(next, {
    'chat-1': 5,
    'chat-2': 0
  })
  assert.equal(isSessionUnread({ id: 'chat-2', messageCount: 2 }, next, true), true)
})

test('visible read receipts use the sidebar session count when it is newer than observed chat detail', () => {
  assert.equal(readMessageCountForVisibleSession({ messageCount: 12 }, 10), 12)
  assert.equal(readMessageCountForVisibleSession({ messageCount: 8 }, 10), 10)
  assert.equal(readMessageCountForVisibleSession(undefined, 7), 7)
})
