import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isSessionUnread, syncInitialReadMessageCounts } from '../app/utils/chatReadReceipts.ts'

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

test('prompt unread keeps a session unread regardless of message count', () => {
  assert.equal(isSessionUnread(
    { id: 'chat-1', messageCount: 3 },
    { 'chat-1': 3 },
    true,
    true
  ), true)
})
