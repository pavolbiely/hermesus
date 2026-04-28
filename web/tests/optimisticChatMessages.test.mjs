import assert from 'node:assert/strict'
import { test } from 'node:test'
import { mergeOptimisticUserMessages } from '../app/utils/optimisticChatMessages.ts'

function message(id, role, text) {
  return {
    id,
    role,
    createdAt: '2026-04-27T12:00:00.000Z',
    parts: text ? [{ type: 'text', text }] : []
  }
}

test('keeps an optimistic user message when the session snapshot is stale', () => {
  const persisted = [message('server-1', 'assistant', 'previous')]
  const optimistic = message('local-1', 'user', 'hello')

  const result = mergeOptimisticUserMessages(
    persisted,
    [...persisted, optimistic],
    new Set(['local-1'])
  )

  assert.deepEqual(result.messages.map(item => item.id), ['server-1', 'local-1'])
  assert.deepEqual([...result.optimisticMessageIds], ['local-1'])
})

test('drops an optimistic user message once an equivalent persisted message appears', () => {
  const persisted = [message('server-1', 'user', 'hello')]
  const optimistic = message('local-1', 'user', 'hello')
  optimistic.createdAt = '2026-04-27T11:59:59.000Z'

  const result = mergeOptimisticUserMessages(
    persisted,
    [optimistic],
    new Set(['local-1'])
  )

  assert.deepEqual(result.messages.map(item => item.id), ['server-1'])
  assert.deepEqual([...result.optimisticMessageIds], [])
})

test('keeps a repeated optimistic user message when only an older equal message is persisted', () => {
  const olderPersisted = message('server-1', 'user', 'hello')
  olderPersisted.createdAt = '2026-04-27T11:59:00.000Z'
  const optimistic = message('local-1', 'user', 'hello')
  optimistic.createdAt = '2026-04-27T12:00:00.000Z'

  const result = mergeOptimisticUserMessages(
    [olderPersisted],
    [olderPersisted, optimistic],
    new Set(['local-1'])
  )

  assert.deepEqual(result.messages.map(item => item.id), ['server-1', 'local-1'])
  assert.deepEqual([...result.optimisticMessageIds], ['local-1'])
})

test('drops an optimistic user message when the persisted message has the same client message id', () => {
  const persisted = message('server-1', 'user', 'different server text')
  persisted.clientMessageId = 'client-1'
  const optimistic = message('local-1', 'user', 'hello')
  optimistic.clientMessageId = 'client-1'

  const result = mergeOptimisticUserMessages(
    [persisted],
    [optimistic],
    new Set(['local-1'])
  )

  assert.deepEqual(result.messages.map(item => item.id), ['server-1'])
  assert.deepEqual([...result.optimisticMessageIds], [])
})

test('keeps a failed local user message when the session snapshot is stale', () => {
  const persisted = [message('server-1', 'assistant', 'previous')]
  const failed = message('local-1', 'user', 'hello')
  failed.clientMessageId = 'client-1'
  failed.localStatus = 'failed'

  const result = mergeOptimisticUserMessages(
    persisted,
    [...persisted, failed],
    new Set(['local-1'])
  )

  assert.deepEqual(result.messages.map(item => item.id), ['server-1', 'local-1'])
  assert.equal(result.messages[1].localStatus, 'failed')
  assert.deepEqual([...result.optimisticMessageIds], ['local-1'])
})

test('does not preserve non-optimistic local messages across session refreshes', () => {
  const persisted = [message('server-1', 'user', 'persisted')]
  const localAssistant = message('local-assistant', 'assistant', 'draft')

  const result = mergeOptimisticUserMessages(
    persisted,
    [...persisted, localAssistant],
    new Set()
  )

  assert.deepEqual(result.messages.map(item => item.id), ['server-1'])
})

test('preserves streaming assistant tool history while a run is active', () => {
  const persisted = [message('server-1', 'user', 'run terminal')]
  const localAssistant = message('local-assistant', 'assistant')
  localAssistant.parts = [
    { type: 'tool', name: 'terminal', status: 'completed' },
    { type: 'tool', name: 'read_file', status: 'running' }
  ]

  const result = mergeOptimisticUserMessages(
    persisted,
    [...persisted, localAssistant],
    new Set(),
    { preserveStreamingAssistant: true }
  )

  assert.deepEqual(result.messages.map(item => item.id), ['server-1', 'local-assistant'])
  assert.deepEqual(result.messages[1].parts, localAssistant.parts)
})
