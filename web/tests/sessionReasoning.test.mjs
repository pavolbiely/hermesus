import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { after, test } from 'node:test'

const tempPaths = []
const modulePromise = loadSessionReasoningModule()

after(async () => {
  await Promise.all(tempPaths.map(path => rm(path, { recursive: true, force: true }).catch(() => undefined)))
})

async function loadSessionReasoningModule() {
  const sourcePath = resolve('server/acp/sessionReasoning.ts')
  const tempPath = resolve(tmpdir(), `hermesum-sessionReasoning.${process.pid}.${randomUUID()}.ts`)
  tempPaths.push(tempPath)

  let source = await readFile(sourcePath, 'utf8')
  source = source.replace("import type { AcpBridgeEvent } from '../../shared/acp/types'\n", '')
  source = source.replace("import type { AcpTurnMetadata } from './turnMetadata'\n", '')
  await mkdir(dirname(tempPath), { recursive: true })
  await writeFile(tempPath, source, 'utf8')
  return import(pathToFileURL(tempPath).href)
}

async function createHermesHome(sessionId, messages) {
  const root = join(tmpdir(), `hermesum-reasoning.${process.pid}.${randomUUID()}`)
  tempPaths.push(root)
  const sessionsDir = join(root, 'sessions')
  await mkdir(sessionsDir, { recursive: true })
  await writeFile(join(sessionsDir, `session_${sessionId}.json`), JSON.stringify({ session_id: sessionId, messages }, null, 2), 'utf8')
  return root
}

test('extracts stored assistant reasoning as replay thought events', async () => {
  const { reasoningEventsFromSessionFile } = await modulePromise
  const sessionId = '20260511_154249_96d548'
  const hermesHome = await createHermesHome(sessionId, [
    { role: 'user', content: 'first' },
    { role: 'assistant', content: '', reasoning: '**First thought**' },
    { role: 'assistant', content: 'first answer' },
    { role: 'user', content: 'second' },
    { role: 'assistant', content: '', reasoning: '**Second thought**' },
    { role: 'assistant', content: 'second answer' }
  ])

  const events = await reasoningEventsFromSessionFile({ hermesHome }, sessionId, [
    { turnId: 'turn-1', userMessageId: 'user-1', completedAt: '2026-05-11T00:00:00.000Z' },
    { turnId: 'turn-2', userMessageId: 'user-2', completedAt: '2026-05-11T00:01:00.000Z' }
  ])

  assert.equal(events.length, 2)
  assert.equal(events[0].turnId, 'turn-1')
  assert.equal(events[0].notification.update.content.text, '**First thought**')
  assert.equal(events[1].turnId, 'turn-2')
  assert.equal(events[1].notification.update.content.text, '**Second thought**')
})

test('uses codex reasoning summaries when raw reasoning is absent', async () => {
  const { latestReasoningEventFromSessionFile } = await modulePromise
  const sessionId = 'summary-session'
  const hermesHome = await createHermesHome(sessionId, [
    { role: 'user', content: 'summarize' },
    {
      role: 'assistant',
      content: '',
      reasoning: null,
      codex_reasoning_items: [
        { type: 'reasoning', summary: [{ type: 'summary_text', text: 'Summary thought' }] }
      ]
    }
  ])

  const event = await latestReasoningEventFromSessionFile({ hermesHome }, sessionId, 'turn-latest')

  assert.ok(event)
  assert.equal(event.turnId, 'turn-latest')
  assert.equal(event.notification.update.content.text, 'Summary thought')
})
