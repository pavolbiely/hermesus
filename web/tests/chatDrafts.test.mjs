import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  NEW_CHAT_DRAFT_ID,
  chatDraftStorageKey,
  readChatDraft,
  writeChatDraft
} from '../app/utils/chatDrafts.ts'

function createStorage() {
  const entries = new Map()
  return {
    getItem: key => entries.has(key) ? entries.get(key) : null,
    setItem: (key, value) => entries.set(key, String(value)),
    removeItem: key => entries.delete(key)
  }
}

test('stores chat drafts under isolated per-chat keys', () => {
  const storage = createStorage()

  writeChatDraft(storage, NEW_CHAT_DRAFT_ID, 'homepage draft')
  writeChatDraft(storage, 'session-a', 'first chat draft')
  writeChatDraft(storage, 'session-b', 'second chat draft')

  assert.equal(readChatDraft(storage, NEW_CHAT_DRAFT_ID), 'homepage draft')
  assert.equal(readChatDraft(storage, 'session-a'), 'first chat draft')
  assert.equal(readChatDraft(storage, 'session-b'), 'second chat draft')
})

test('removes empty drafts without affecting other chats', () => {
  const storage = createStorage()

  writeChatDraft(storage, 'session-a', 'first chat draft')
  writeChatDraft(storage, 'session-b', 'second chat draft')
  writeChatDraft(storage, 'session-a', '')

  assert.equal(readChatDraft(storage, 'session-a'), '')
  assert.equal(readChatDraft(storage, 'session-b'), 'second chat draft')
})

test('encodes draft ids in localStorage keys', () => {
  assert.equal(
    chatDraftStorageKey('chat/id with spaces'),
    'hermesum:web-chat:draft:v1:chat%2Fid%20with%20spaces'
  )
})
