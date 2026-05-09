import assert from 'node:assert/strict'
import { test } from 'node:test'
import { applySessionMessageUpdate } from '../app/utils/sessionMessageUpdates.ts'

function snapshot(messages, messagesTotal = messages.length) {
  return {
    session: { id: 'session-1' },
    messages,
    messagesTotal
  }
}

test('appends a missing message and increments known message total', () => {
  const result = applySessionMessageUpdate(snapshot([{ id: 'a', role: 'user', parts: [] }], 1), { id: 'b', role: 'user', parts: [] }, 'append')

  assert.deepEqual(result.messages.map(message => message.id), ['a', 'b'])
  assert.equal(result.messagesTotal, 2)
})

test('replaces an optimistic message by client message id', () => {
  const optimistic = { id: 'local-1', clientMessageId: 'client-1', role: 'user', localStatus: 'sending', parts: [] }
  const canonical = { id: 'server-1', clientMessageId: 'client-1', role: 'user', parts: [] }
  const result = applySessionMessageUpdate(snapshot([optimistic]), canonical, 'replace')

  assert.deepEqual(result.messages, [canonical])
})

test('does not append missing messages in replace mode', () => {
  const original = snapshot([{ id: 'a', role: 'user', parts: [] }], 1)
  const result = applySessionMessageUpdate(original, { id: 'b', role: 'user', parts: [] }, 'replace')

  assert.equal(result, original)
})
