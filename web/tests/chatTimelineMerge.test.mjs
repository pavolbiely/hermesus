import assert from 'node:assert/strict'
import { test } from 'node:test'
import { mergeChatTimeline } from '../app/utils/chatTimelineMerge.ts'

function message(id, role, text, identity = {}) {
  return {
    id,
    role,
    createdAt: '2026-04-27T12:00:00.000Z',
    parts: text ? [{ type: 'text', text }] : [],
    ...identity
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

test('does not drop an optimistic user message by matching text and time', () => {
  const persisted = [message('server-1', 'user', 'hello')]
  const optimistic = message('local-1', 'user', 'hello')
  optimistic.createdAt = '2026-04-27T11:59:59.000Z'

  const result = mergeChatTimeline(
    persisted,
    [optimistic],
    new Set(['local-1'])
  )

  assert.deepEqual(result.messages.map(item => item.id), ['server-1', 'local-1'])
  assert.deepEqual([...result.optimisticMessageIds], ['local-1'])
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
  const persisted = [message('server-1', 'user', 'run terminal', { runId: 'run-1', turnId: 'run-1' })]
  const localAssistant = message('local-assistant', 'assistant', '', { runId: 'run-1', turnId: 'run-1' })
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
  const persisted = [message('server-1', 'user', 'please fix it', { runId: 'run-1', turnId: 'run-1' })]
  const completedAssistant = message('local-assistant', 'assistant', 'fixed', { runId: 'run-1', turnId: 'run-1' })

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
    message('server-1', 'user', 'please fix it', { runId: 'run-1', turnId: 'run-1' }),
    message('server-assistant', 'assistant', 'fixed', { runId: 'run-1', turnId: 'run-1' })
  ]
  const completedAssistant = message('local-assistant', 'assistant', 'fixed', { runId: 'run-1', turnId: 'run-1' })
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
    message('server-1', 'user', 'please fix it', { runId: 'run-1', turnId: 'run-1' }),
    message('server-assistant', 'assistant', 'fixed with final persisted content', { runId: 'run-1', turnId: 'run-1' })
  ]
  const completedAssistant = message('local-assistant', 'assistant', 'fixed', { runId: 'run-1', turnId: 'run-1' })
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

test('drops a preserved completed assistant once the same run is persisted regardless of text', () => {
  const persisted = [
    message('server-1', 'user', 'please fix it', { runId: 'run-1', turnId: 'run-1' }),
    message('server-assistant', 'assistant', 'fixed with final persisted content', { runId: 'run-1', turnId: 'run-1' })
  ]
  const completedAssistant = message('local-assistant', 'assistant', 'fixed', { runId: 'run-1', turnId: 'run-1' })
  completedAssistant.createdAt = '2026-04-27T11:59:59.000Z'

  const result = mergeChatTimeline(
    persisted,
    [...persisted.slice(0, 1), completedAssistant],
    new Set(),
    { preserveAssistantMessageIds: new Set(['local-assistant']) }
  )

  assert.deepEqual(result.messages.map(item => item.id), ['server-1', 'server-assistant'])
  assert.deepEqual([...result.preservedAssistantMessageIds], [])
})

test('keeps a preserved assistant with its run turn when a newer user message is already persisted', () => {
  const olderUser = message('server-user-1', 'user', 'first turn', { runId: 'run-1', turnId: 'run-1' })
  const localAssistant = message('local-assistant-1', 'assistant', 'done', { runId: 'run-1', turnId: 'run-1' })
  const newUser = message('server-user-2', 'user', 'second turn', { runId: 'run-2', turnId: 'run-2' })

  const result = mergeChatTimeline(
    [olderUser, newUser],
    [olderUser, localAssistant, newUser],
    new Set(),
    { preserveAssistantMessageIds: new Set(['local-assistant-1']) }
  )

  assert.deepEqual(result.messages.map(item => item.id), [
    'server-user-1',
    'local-assistant-1',
    'server-user-2'
  ])
  assert.deepEqual([...result.preservedAssistantMessageIds], ['local-assistant-1'])
})

test('places a preserved assistant by run identity when user text repeats', () => {
  const firstUser = message('server-user-1', 'user', 'repeat', { runId: 'run-1', turnId: 'run-1' })
  const secondUser = message('server-user-2', 'user', 'repeat', { runId: 'run-2', turnId: 'run-2' })
  const localAssistant = message('local-assistant-2', 'assistant', 'second answer', { runId: 'run-2', turnId: 'run-2' })

  const result = mergeChatTimeline(
    [firstUser, secondUser],
    [firstUser, secondUser, localAssistant],
    new Set(),
    { preserveAssistantMessageIds: new Set(['local-assistant-2']) }
  )

  assert.deepEqual(result.messages.map(item => item.id), [
    'server-user-1',
    'server-user-2',
    'local-assistant-2'
  ])
})

test('drops an older preserved assistant after its turn persists and a newer user message is appended', () => {
  const olderUser = message('server-user-1', 'user', 'first turn', { runId: 'run-1', turnId: 'run-1' })
  const persistedAssistant = message('server-assistant-1', 'assistant', 'done', { runId: 'run-1', turnId: 'run-1' })
  persistedAssistant.createdAt = '2026-04-27T12:00:01.000Z'
  const newUser = message('server-user-2', 'user', 'second turn', { runId: 'run-2', turnId: 'run-2' })
  const localAssistant = message('local-assistant-1', 'assistant', 'done', { runId: 'run-1', turnId: 'run-1' })
  localAssistant.createdAt = '2026-04-27T12:00:12.000Z'

  const result = mergeChatTimeline(
    [olderUser, persistedAssistant, newUser],
    [olderUser, localAssistant, newUser],
    new Set(),
    { preserveAssistantMessageIds: new Set(['local-assistant-1']) }
  )

  assert.deepEqual(result.messages.map(item => item.id), [
    'server-user-1',
    'server-assistant-1',
    'server-user-2'
  ])
  assert.deepEqual([...result.preservedAssistantMessageIds], [])
})

test('keeps a repeated preserved assistant when the same text is only persisted for an older turn', () => {
  const olderUser = message('server-user-1', 'user', 'reply exactly OK', { runId: 'run-1', turnId: 'run-1' })
  const olderAssistant = message('server-assistant-1', 'assistant', 'OK', { runId: 'run-1', turnId: 'run-1' })
  const currentUser = message('server-user-2', 'user', 'reply exactly OK again', { runId: 'run-2', turnId: 'run-2' })
  const completedAssistant = message('local-assistant', 'assistant', 'OK', { runId: 'run-2', turnId: 'run-2' })
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
