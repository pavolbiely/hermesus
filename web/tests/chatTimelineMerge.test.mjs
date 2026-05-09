import assert from 'node:assert/strict'
import { test } from 'node:test'
import { mergeChatTimeline } from '../app/utils/chatTimelineMerge.ts'

function message(id, role, text) {
  return {
    id,
    role,
    createdAt: '2026-04-27T12:00:00.000Z',
    parts: text ? [{ type: 'text', text }] : []
  }
}

function systemEvent(id, eventType, title) {
  return {
    id,
    role: 'system',
    createdAt: '2026-04-27T12:00:00.000Z',
    parts: [{ type: 'event', eventType, title }]
  }
}

test('keeps an optimistic user message when the session snapshot is stale', () => {
  const persisted = [message('server-1', 'assistant', 'previous')]
  const optimistic = message('local-1', 'user', 'hello')

  const result = mergeChatTimeline(
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

  const result = mergeChatTimeline(
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

  const result = mergeChatTimeline(
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

  const result = mergeChatTimeline(
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

  const result = mergeChatTimeline(
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

  const result = mergeChatTimeline(
    persisted,
    [...persisted, localAssistant],
    new Set()
  )

  assert.deepEqual(result.messages.map(item => item.id), ['server-1'])
})

test('preserves local system events across session refreshes', () => {
  const persisted = [message('server-1', 'user', 'persisted')]
  const event = systemEvent('local-event', 'run_stopped', 'Run stopped')

  const result = mergeChatTimeline(
    persisted,
    [...persisted, event],
    new Set()
  )

  assert.deepEqual(result.messages.map(item => item.id), ['server-1', 'local-event'])
})

test('does not duplicate equivalent system events after persistence', () => {
  const persisted = [systemEvent('server-event', 'run_stopped', 'Run stopped')]
  const local = systemEvent('local-event', 'run_stopped', 'Run stopped')

  const result = mergeChatTimeline(
    persisted,
    [...persisted, local],
    new Set()
  )

  assert.deepEqual(result.messages.map(item => item.id), ['server-event'])
})

test('preserves streaming assistant tool history while a run is active', () => {
  const persisted = [message('server-1', 'user', 'run terminal')]
  const localAssistant = message('local-assistant', 'assistant')
  localAssistant.parts = [
    { type: 'tool', name: 'terminal', status: 'completed' },
    { type: 'tool', name: 'read_file', status: 'running' }
  ]

  const result = mergeChatTimeline(
    persisted,
    [...persisted, localAssistant],
    new Set(),
    { preserveStreamingAssistant: true }
  )

  assert.deepEqual(result.messages.map(item => item.id), ['server-1', 'local-assistant'])
  assert.deepEqual(result.messages[1].parts, localAssistant.parts)
})

test('preserves a just-completed assistant message when the terminal session snapshot is stale', () => {
  const persisted = [message('server-1', 'user', 'please fix it')]
  const completedAssistant = message('local-assistant', 'assistant', 'fixed')

  const result = mergeChatTimeline(
    persisted,
    [...persisted, completedAssistant],
    new Set(),
    { preserveAssistantMessageIds: new Set(['local-assistant']) }
  )

  assert.deepEqual(result.messages.map(item => item.id), ['server-1', 'local-assistant'])
  assert.deepEqual([...result.preservedAssistantMessageIds], ['local-assistant'])
})

test('drops a preserved completed assistant once an equivalent persisted message appears', () => {
  const persisted = [
    message('server-1', 'user', 'please fix it'),
    message('server-assistant', 'assistant', 'fixed')
  ]
  const completedAssistant = message('local-assistant', 'assistant', 'fixed')
  completedAssistant.createdAt = '2026-04-27T11:59:59.000Z'

  const result = mergeChatTimeline(
    persisted,
    [...persisted, completedAssistant],
    new Set(),
    { preserveAssistantMessageIds: new Set(['local-assistant']) }
  )

  assert.deepEqual(result.messages.map(item => item.id), ['server-1', 'server-assistant'])
  assert.deepEqual([...result.preservedAssistantMessageIds], [])
})

test('drops a preserved completed assistant once a newer persisted assistant appears', () => {
  const persisted = [
    message('server-1', 'user', 'please fix it'),
    message('server-assistant', 'assistant', 'fixed with final persisted content')
  ]
  const completedAssistant = message('local-assistant', 'assistant', 'fixed')
  completedAssistant.createdAt = '2026-04-27T11:59:59.000Z'

  const result = mergeChatTimeline(
    persisted,
    [...persisted, completedAssistant],
    new Set(),
    { preserveAssistantMessageIds: new Set(['local-assistant']) }
  )

  assert.deepEqual(result.messages.map(item => item.id), ['server-1', 'server-assistant'])
  assert.deepEqual([...result.preservedAssistantMessageIds], [])
})

test('drops a preserved completed assistant when the same turn is already persisted with an older timestamp', () => {
  const user = message('server-user', 'user', 'reply exactly OK3')
  user.createdAt = '2026-04-27T12:00:00.000Z'
  const persistedAssistant = message('server-assistant', 'assistant', 'OK3')
  persistedAssistant.createdAt = '2026-04-27T12:00:01.000Z'
  const completedAssistant = message('local-assistant', 'assistant', 'OK3')
  completedAssistant.createdAt = '2026-04-27T12:00:12.000Z'

  const result = mergeChatTimeline(
    [user, persistedAssistant],
    [user, completedAssistant],
    new Set(),
    { preserveAssistantMessageIds: new Set(['local-assistant']) }
  )

  assert.deepEqual(result.messages.map(item => item.id), ['server-user', 'server-assistant'])
  assert.deepEqual([...result.preservedAssistantMessageIds], [])
})

test('keeps a repeated preserved assistant when the same text is only persisted for an older turn', () => {
  const olderUser = message('server-user-1', 'user', 'reply exactly OK')
  const olderAssistant = message('server-assistant-1', 'assistant', 'OK')
  const currentUser = message('server-user-2', 'user', 'reply exactly OK again')
  const completedAssistant = message('local-assistant', 'assistant', 'OK')
  completedAssistant.createdAt = '2026-04-27T12:00:12.000Z'

  const result = mergeChatTimeline(
    [olderUser, olderAssistant, currentUser],
    [olderUser, olderAssistant, currentUser, completedAssistant],
    new Set(),
    { preserveAssistantMessageIds: new Set(['local-assistant']) }
  )

  assert.deepEqual(result.messages.map(item => item.id), [
    'server-user-1',
    'server-assistant-1',
    'server-user-2',
    'local-assistant'
  ])
  assert.deepEqual([...result.preservedAssistantMessageIds], ['local-assistant'])
})
