import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { mkdir, readFile, unlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { after, test } from 'node:test'

const tempModules = []
const projectionModule = loadProjectionModule()

after(async () => {
  await Promise.all(tempModules.map(path => unlink(path).catch(() => undefined)))
})

async function loadProjectionModule() {
  const sourcePath = resolve('server/acp/transcriptProjection.ts')
  const tempPath = resolve(tmpdir(), `hermesum-transcriptProjection.${process.pid}.${randomUUID()}.ts`)
  tempModules.push(tempPath)
  const replacements = new Map([
    ['../../shared/acp/eventNormalization', pathToFileURL(resolve('shared/acp/eventNormalization.ts')).href],
    ['../../shared/acp/bridgeEventNormalization', pathToFileURL(resolve('shared/acp/bridgeEventNormalization.ts')).href],
    ['../../shared/acp/planNormalization', pathToFileURL(resolve('shared/acp/planNormalization.ts')).href],
    ['../../shared/acp/types', pathToFileURL(resolve('shared/acp/types.ts')).href],
    ['./transcriptStore', pathToFileURL(resolve('server/acp/transcriptStore.ts')).href]
  ])

  let source = await readFile(sourcePath, 'utf8')
  for (const [from, to] of replacements) source = source.replaceAll(`'${from}'`, `'${to}'`)
  await mkdir(dirname(tempPath), { recursive: true })
  await writeFile(tempPath, source, 'utf8')
  return import(pathToFileURL(tempPath).href)
}

function memoryStore(initial = null) {
  let snapshot = initial
  return {
    async get() {
      return snapshot ? structuredClone(snapshot) : null
    },
    async put(value) {
      snapshot = structuredClone(value)
    },
    async delete() {
      snapshot = null
    },
    async listSessionIds() {
      return snapshot ? [snapshot.sessionId] : []
    },
    read() {
      return snapshot
    }
  }
}

function deferred() {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

function sessionUpdate(sessionId, update, extra = {}) {
  return {
    type: 'session.update',
    sessionId,
    sequence: extra.sequence,
    turnId: extra.turnId,
    messageId: extra.messageId,
    notification: { sessionId, update }
  }
}

test('projection applies bridge events through shared transcript reducer', async () => {
  const { updateProjectionFromEvent } = await projectionModule
  const store = memoryStore()
  const sessionId = 'projection-session'
  const turnId = 'turn-1'

  await updateProjectionFromEvent({
    type: 'prompt.started',
    sessionId,
    sequence: 1,
    turnId,
    messageId: 'user-1',
    message: 'Hello'
  }, store)

  await updateProjectionFromEvent(sessionUpdate(sessionId, {
    sessionUpdate: 'agent_message_chunk',
    content: { type: 'text', text: 'Hi' },
    messageId: 'assistant-1'
  }, { sequence: 2, turnId }), store)

  await updateProjectionFromEvent({
    type: 'prompt.completed',
    sessionId,
    sequence: 3,
    turnId,
    messageId: 'assistant-1',
    userMessageId: 'user-1',
    completedAt: '2026-05-11T10:00:00.000Z',
    response: {
      stopReason: 'end_turn',
      userMessageId: 'user-1',
      usage: { totalTokens: 8, inputTokens: 3, outputTokens: 5 }
    }
  }, store)

  const stored = store.read()
  assert.equal(stored.cursor, 3)
  assert.equal(stored.messages.length, 2)
  assert.equal(stored.messages[0].role, 'user')
  assert.equal(stored.messages[0].parts[0].text, 'Hello')
  assert.equal(stored.messages[1].role, 'assistant')
  assert.equal(stored.messages[1].id, 'assistant-1')
  assert.equal(stored.messages[1].parts[0].text, 'Hi')
  assert.equal(stored.messages[1].completedAt, '2026-05-11T10:00:00.000Z')
  assert.equal(stored.messages[1].usage.totalTokens, 8)
})

test('projection rebuilds a session-load snapshot from replay events and metadata', async () => {
  const { rebuildAcpProjection } = await projectionModule
  const store = memoryStore()
  const sessionId = 'rebuild-session'

  await rebuildAcpProjection(sessionId, [{
    type: 'prompt.started',
    sessionId,
    sequence: 1,
    turnId: 'turn-1',
    messageId: 'user-1',
    message: 'Loaded prompt'
  }, sessionUpdate(sessionId, {
    sessionUpdate: 'agent_message_chunk',
    content: { type: 'text', text: 'Loaded answer' },
    messageId: 'assistant-1'
  }, { sequence: 2, turnId: 'turn-1' }), {
    type: 'prompt.completed',
    sessionId,
    turnId: 'turn-1',
    messageId: 'assistant-1',
    userMessageId: 'user-1',
    completedAt: '2026-05-11T10:01:00.000Z',
    response: { stopReason: 'end_turn', userMessageId: 'user-1' }
  }], {
    models: { currentModelId: 'gpt-5.5', availableModels: [{ modelId: 'gpt-5.5', name: 'GPT 5.5' }] },
    modes: { currentModeId: 'chat', availableModes: [{ id: 'chat', name: 'Chat' }] },
    configOptions: [{ id: 'reasoning', name: 'Reasoning', type: 'select', currentValue: 'low', options: [] }]
  }, store)

  const stored = store.read()
  assert.equal(stored.sessionId, sessionId)
  assert.equal(stored.cursor, 2)
  assert.equal(stored.messages.length, 2)
  assert.equal(stored.messages[1].parts[0].text, 'Loaded answer')
  assert.equal(stored.prompt.status, 'completed')
  assert.equal(stored.models.currentModelId, 'gpt-5.5')
  assert.equal(stored.modes.currentModeId, 'chat')
  assert.equal(stored.configOptions[0].id, 'reasoning')
})

test('projection mirrors prompt terminal state', async () => {
  const { applyAcpProjectionEvent, createEmptySnapshot } = await projectionModule
  const sessionId = 'prompt-state-session'
  let snapshot = createEmptySnapshot(sessionId)

  snapshot = applyAcpProjectionEvent(snapshot, {
    type: 'prompt.started',
    sessionId,
    sequence: 1,
    turnId: 'turn-1',
    messageId: 'user-1',
    message: 'Hello'
  })
  assert.equal(snapshot.prompt.status, 'running')
  assert.equal(snapshot.prompt.turnId, 'turn-1')

  snapshot = applyAcpProjectionEvent(snapshot, {
    type: 'prompt.failed',
    sessionId,
    sequence: 2,
    turnId: 'turn-1',
    messageId: 'assistant-1',
    error: 'boom'
  })
  assert.equal(snapshot.prompt.status, 'failed')
  assert.equal(snapshot.prompt.error, 'boom')

  snapshot = applyAcpProjectionEvent(snapshot, {
    type: 'prompt.cancelled',
    sessionId,
    sequence: 3
  })
  assert.equal(snapshot.prompt.status, 'cancelled')
})

test('projection mirrors permission and metadata updates', async () => {
  const { applyAcpProjectionEvent, createEmptySnapshot } = await projectionModule
  const sessionId = 'metadata-session'
  let snapshot = {
    ...createEmptySnapshot(sessionId),
    modes: { currentModeId: 'chat', availableModes: [{ id: 'chat', name: 'Chat' }, { id: 'plan', name: 'Plan' }] }
  }

  snapshot = applyAcpProjectionEvent(snapshot, {
    type: 'permission.requested',
    sessionId,
    sequence: 1,
    appRequestId: 'permission-1',
    request: {
      sessionId,
      toolCall: { toolCallId: 'tool-1', title: 'Run command' },
      options: [{ optionId: 'deny', name: 'Deny', kind: 'reject_once' }]
    }
  })
  assert.equal(snapshot.pendingPermissions.length, 1)

  snapshot = applyAcpProjectionEvent(snapshot, sessionUpdate(sessionId, {
    sessionUpdate: 'plan',
    entries: [
      { content: 'Implement projection', status: 'in_progress', priority: 'high' },
      { content: '', status: 'pending', priority: 'low' }
    ]
  }, { sequence: 2 }))
  assert.deepEqual(snapshot.planEntries, [{ content: 'Implement projection', status: 'in_progress', priority: 'high' }])

  snapshot = applyAcpProjectionEvent(snapshot, sessionUpdate(sessionId, {
    sessionUpdate: 'current_mode_update',
    currentModeId: 'plan'
  }, { sequence: 3 }))
  assert.equal(snapshot.modes.currentModeId, 'plan')

  snapshot = applyAcpProjectionEvent(snapshot, sessionUpdate(sessionId, {
    sessionUpdate: 'config_option_update',
    configOptions: [{ id: 'reasoning', name: 'Reasoning', type: 'select', currentValue: 'high', options: [] }]
  }, { sequence: 4 }))
  assert.equal(snapshot.configOptions[0].id, 'reasoning')

  snapshot = applyAcpProjectionEvent(snapshot, sessionUpdate(sessionId, {
    sessionUpdate: 'available_commands_update',
    availableCommands: [{ name: 'commit', description: 'Commit changes' }]
  }, { sequence: 5 }))
  assert.equal(snapshot.availableCommands[0].name, 'commit')

  snapshot = applyAcpProjectionEvent(snapshot, {
    type: 'permission.resolved',
    sessionId,
    sequence: 6,
    appRequestId: 'permission-1',
    response: { outcome: 'cancelled' }
  })
  assert.deepEqual(snapshot.pendingPermissions, [])
})

test('record queues concurrent same-session writes and swallows persistence failures', async () => {
  const { recordAcpProjectionEvent } = await projectionModule
  const warn = console.warn
  const warnings = []
  const firstPutStarted = deferred()
  const releaseFirstPut = deferred()
  const writes = []
  const store = {
    async get() {
      return writes.at(-1) ?? null
    },
    async put(value) {
      writes.push(structuredClone(value))
      if (writes.length === 1) {
        firstPutStarted.resolve()
        await releaseFirstPut.promise
        throw new Error('disk unavailable')
      }
    },
    async delete() {},
    async listSessionIds() { return [] }
  }

  console.warn = (...args) => warnings.push(args)
  try {
    const first = recordAcpProjectionEvent({
      type: 'prompt.started',
      sessionId: 'safe-session',
      sequence: 1,
      turnId: 'turn-1',
      messageId: 'user-1',
      message: 'First write fails but does not reject'
    }, store)
    await firstPutStarted.promise

    const second = recordAcpProjectionEvent({
      type: 'prompt.started',
      sessionId: 'safe-session',
      sequence: 2,
      turnId: 'turn-2',
      messageId: 'user-2',
      message: 'Second write still runs'
    }, store)

    assert.equal(writes.length, 1)
    releaseFirstPut.resolve()
    await Promise.all([first, second])
  } finally {
    console.warn = warn
  }

  assert.equal(writes.length, 2)
  assert.equal(warnings.length, 1)
  assert.equal(writes[1].messages.length, 2)
  assert.equal(writes[1].messages[1].id, 'user-2')
})
