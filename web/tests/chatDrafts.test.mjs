import test from 'node:test'
import assert from 'node:assert/strict'
import {
  NEW_CHAT_DRAFT_ID,
  chatDraftStorageKey,
  chatSessionDraftId,
  readChatDraft,
  writeChatDraft
} from '../app/utils/chatDrafts.ts'

function createStorage() {
  const items = new Map()
  return {
    getItem: key => items.get(key) ?? null,
    setItem: (key, value) => items.set(key, String(value)),
    removeItem: key => items.delete(key)
  }
}

test('uses distinct stable draft ids for new chat and sessions', () => {
  assert.equal(NEW_CHAT_DRAFT_ID, 'new-chat')
  assert.equal(chatSessionDraftId('abc-123'), 'acp-session:abc-123')
  assert.notEqual(chatSessionDraftId('new-chat'), NEW_CHAT_DRAFT_ID)
})

test('encodes arbitrary draft ids in storage keys', () => {
  assert.equal(
    chatDraftStorageKey('acp-session:abc/123?x=1'),
    'hermesum:web-chat:draft:v1:acp-session%3Aabc%2F123%3Fx%3D1'
  )
})

test('reads, writes, and clears draft text', () => {
  const storage = createStorage()
  const draftId = chatSessionDraftId('session-a')

  assert.equal(readChatDraft(storage, draftId), '')

  writeChatDraft(storage, draftId, 'unfinished prompt')
  assert.equal(readChatDraft(storage, draftId), 'unfinished prompt')

  writeChatDraft(storage, draftId, '')
  assert.equal(readChatDraft(storage, draftId), '')
})

test('keeps drafts isolated by scope', () => {
  const storage = createStorage()
  const newChatDraft = NEW_CHAT_DRAFT_ID
  const sessionDraft = chatSessionDraftId('session-a')

  writeChatDraft(storage, newChatDraft, 'new chat text')
  writeChatDraft(storage, sessionDraft, 'session text')

  assert.equal(readChatDraft(storage, newChatDraft), 'new chat text')
  assert.equal(readChatDraft(storage, sessionDraft), 'session text')
})

test('storage failures are best-effort', () => {
  const storage = {
    getItem: () => { throw new Error('blocked') },
    setItem: () => { throw new Error('blocked') },
    removeItem: () => { throw new Error('blocked') }
  }

  assert.equal(readChatDraft(storage, chatSessionDraftId('session-a')), '')
  assert.doesNotThrow(() => writeChatDraft(storage, chatSessionDraftId('session-a'), 'text'))
})
