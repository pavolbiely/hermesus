import test from 'node:test'
import assert from 'node:assert/strict'
import {
  createQueuedMessage,
  nextQueuedMessage,
  removeQueuedMessage,
  updateQueuedMessage
} from '../app/utils/queuedMessages.ts'

test('creates a trimmed queued message', () => {
  const message = createQueuedMessage({ sessionId: 's1', text: '  hello  ', id: 'q1', now: 'now' })

  assert.equal(message.text, 'hello')
  assert.equal(message.sessionId, 's1')
  assert.equal(message.id, 'q1')
  assert.equal(message.createdAt, 'now')
  assert.equal(message.updatedAt, 'now')
})

test('rejects empty queued messages', () => {
  assert.equal(createQueuedMessage({ sessionId: 's1', text: '   ', id: 'q1', now: 'now' }), null)
})

test('updates and removes queued messages immutably', () => {
  const original = [createQueuedMessage({ sessionId: 's1', text: 'one', id: 'q1', now: 't1' })]
  const updated = updateQueuedMessage(original, 'q1', 'two', 't2')

  assert.equal(updated[0].text, 'two')
  assert.equal(updated[0].updatedAt, 't2')
  assert.equal(original[0].text, 'one')
  assert.deepEqual(removeQueuedMessage(updated, 'q1'), [])
})

test('drops queued message when updated to blank text', () => {
  const original = [createQueuedMessage({ sessionId: 's1', text: 'one', id: 'q1', now: 't1' })]

  assert.deepEqual(updateQueuedMessage(original, 'q1', '   ', 't2'), [])
})

test('returns next queued message for a session in FIFO order', () => {
  const messages = [
    createQueuedMessage({ sessionId: 's2', text: 'other', id: 'q0', now: 't0' }),
    createQueuedMessage({ sessionId: 's1', text: 'first', id: 'q1', now: 't1' }),
    createQueuedMessage({ sessionId: 's1', text: 'second', id: 'q2', now: 't2' })
  ]

  assert.equal(nextQueuedMessage(messages, 's1')?.id, 'q1')
}
)
