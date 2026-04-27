import assert from 'node:assert/strict'
import { test } from 'node:test'
import { markLocalMessageFailed, markLocalMessageSending, removeLocalMessage } from '../app/utils/failedChatMessages.ts'

function message(id, text = 'hello') {
  return {
    id,
    role: 'user',
    createdAt: '2026-04-27T12:00:00.000Z',
    clientMessageId: `client-${id}`,
    parts: [{ type: 'text', text }]
  }
}

test('marks a local user message as failed without removing it', () => {
  const messages = [message('local-1')]

  const result = markLocalMessageFailed(messages, 'local-1', 'Network unavailable')

  assert.equal(result.length, 1)
  assert.equal(result[0].id, 'local-1')
  assert.equal(result[0].localStatus, 'failed')
  assert.equal(result[0].localError, 'Network unavailable')
})

test('marks a failed local user message as sending for retry', () => {
  const failed = message('local-1')
  failed.localStatus = 'failed'
  failed.localError = 'Network unavailable'

  const result = markLocalMessageSending([failed], 'local-1')

  assert.equal(result[0].localStatus, 'sending')
  assert.equal(result[0].localError, undefined)
})

test('removes a local failed message when editing it back into the composer', () => {
  const result = removeLocalMessage([message('local-1'), message('local-2')], 'local-1')

  assert.deepEqual(result.map(item => item.id), ['local-2'])
})
