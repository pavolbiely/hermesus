import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import {
  createFileAcpTranscriptStore,
  decodeSessionId,
  encodeSessionId
} from '../server/acp/transcriptStore.ts'

async function withStore(fn) {
  const directory = await mkdtemp(join(tmpdir(), 'hermesum-transcripts-'))
  try {
    return await fn(createFileAcpTranscriptStore({ directory }), directory)
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
}

function snapshot(sessionId = 'session/with:unsafe chars') {
  return {
    sessionId,
    cursor: 42,
    updatedAt: '2026-05-11T00:00:00.000Z',
    messages: [{
      id: 'message-1',
      role: 'assistant',
      sessionId,
      turnId: 'turn-1',
      createdAt: '2026-05-11T00:00:00.000Z',
      parts: [{ type: 'text', text: 'Stored transcript' }]
    }],
    pendingPermissions: [],
    planEntries: [],
    prompt: null,
    models: null,
    modes: null,
    configOptions: [],
    availableCommands: []
  }
}

test('encodes session ids losslessly for filenames', () => {
  const sessionId = 'profile/session:with/slashes and spaces'
  assert.equal(decodeSessionId(encodeSessionId(sessionId)), sessionId)
  assert.match(encodeSessionId(sessionId), /^[A-Za-z0-9_-]+$/)
})

test('stores and reads transcript snapshots', async () => {
  await withStore(async (store, directory) => {
    const value = snapshot()
    await store.put(value)

    assert.deepEqual(await store.get(value.sessionId), value)
    assert.deepEqual(await store.listSessionIds(), [value.sessionId])

    const file = join(directory, `${encodeSessionId(value.sessionId)}.json`)
    const raw = await readFile(file, 'utf8')
    assert.equal(JSON.parse(raw).sessionId, value.sessionId)
  })
})

test('delete removes only the stored projection', async () => {
  await withStore(async (store) => {
    const value = snapshot('session-to-delete')
    await store.put(value)
    await store.delete(value.sessionId)

    assert.equal(await store.get(value.sessionId), null)
    assert.deepEqual(await store.listSessionIds(), [])
  })
})

test('invalid or mismatched projection files are ignored on read', async () => {
  await withStore(async (store, directory) => {
    const sessionId = 'expected-session'
    const file = join(directory, `${encodeSessionId(sessionId)}.json`)
    await writeFile(file, JSON.stringify({ ...snapshot('different-session') }), 'utf8')

    assert.equal(await store.get(sessionId), null)

    await writeFile(file, '{not valid json', 'utf8')
    assert.equal(await store.get(sessionId), null)
  })
})

test('blank session ids are rejected', async () => {
  await withStore(async (store) => {
    await assert.rejects(() => store.put(snapshot('')), /session id is required/)
    await assert.rejects(() => store.get(''), /session id is required/)
  })
})
