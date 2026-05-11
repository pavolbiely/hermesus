import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { mkdir, readFile, unlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { after, test } from 'node:test'

const tempModules = []
const eventsModule = loadEventsModule()

after(async () => {
  await Promise.all(tempModules.map(path => unlink(path).catch(() => undefined)))
})

async function loadEventsModule() {
  const projectionStubPath = resolve(tmpdir(), `hermesum-events-projection.${process.pid}.${randomUUID()}.ts`)
  const eventsPath = resolve(tmpdir(), `hermesum-events.${process.pid}.${randomUUID()}.ts`)
  tempModules.push(projectionStubPath, eventsPath)

  await mkdir(dirname(eventsPath), { recursive: true })
  await writeFile(projectionStubPath, 'export function recordAcpProjectionEvent() { return Promise.resolve() }\n', 'utf8')

  let source = await readFile(resolve('server/acp/events.ts'), 'utf8')
  source = source.replaceAll(
    "'../../shared/acp/types'",
    `'${pathToFileURL(resolve('shared/acp/types.ts')).href}'`
  )
  source = source.replaceAll(
    "'./transcriptProjection'",
    `'${pathToFileURL(projectionStubPath).href}'`
  )
  await writeFile(eventsPath, source, 'utf8')
  return import(pathToFileURL(eventsPath).href)
}

test('publishAcpEvent keeps delivering when a subscriber throws', async () => {
  const { publishAcpEvent, replayAcpSession, subscribeAcpSession } = await eventsModule
  const sessionId = `events-session-${randomUUID()}`
  const warn = console.warn
  const warnings = []
  const received = []

  console.warn = (...args) => warnings.push(args)
  try {
    const unsubscribeThrowing = subscribeAcpSession(sessionId, () => {
      throw new Error('subscriber failed')
    })
    const unsubscribeReceiving = subscribeAcpSession(sessionId, event => {
      received.push(event)
    })

    publishAcpEvent({
      type: 'prompt.started',
      sessionId,
      turnId: 'turn-1',
      messageId: 'message-1',
      message: 'hello'
    })

    unsubscribeThrowing()
    unsubscribeReceiving()
  } finally {
    console.warn = warn
  }

  assert.equal(warnings.length, 1)
  assert.equal(received.length, 1)
  assert.equal(received[0].sequence, 1)
  assert.deepEqual(replayAcpSession(sessionId), received)
})

test('ensureAcpSessionSequenceAtLeast prevents post-restart sequence rewind', async () => {
  const { ensureAcpSessionSequenceAtLeast, publishAcpEvent, replayAcpSession } = await eventsModule
  const sessionId = `events-session-${randomUUID()}`

  ensureAcpSessionSequenceAtLeast(sessionId, 42)
  publishAcpEvent({
    type: 'prompt.started',
    sessionId,
    turnId: 'turn-1',
    messageId: 'message-1',
    message: 'hello'
  })

  assert.equal(replayAcpSession(sessionId).at(-1)?.sequence, 43)
})
