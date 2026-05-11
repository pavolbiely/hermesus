import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { after, test } from 'node:test'

const tempModules = []
const modulePromise = loadAcpRunDetailsModule()

after(async () => {
  await Promise.all(tempModules.map(path => rm(path, { recursive: true, force: true }).catch(() => undefined)))
})

async function loadAcpRunDetailsModule() {
  const sourcePath = resolve('app/utils/acpRunDetails.ts')
  const tempPath = resolve(tmpdir(), `hermesum-acpRunDetails.${process.pid}.${randomUUID()}.ts`)
  tempModules.push(tempPath)

  let source = await readFile(sourcePath, 'utf8')
  source = source.replace("import type { AcpChatMessage, AcpChatPart } from '../types/acp-chat'\n", '')
  await mkdir(dirname(tempPath), { recursive: true })
  await writeFile(tempPath, source, 'utf8')
  return import(pathToFileURL(tempPath).href)
}

function tool(toolCallId, name) {
  return {
    type: 'tool',
    toolCallId,
    name,
    state: 'completed',
    status: 'completed'
  }
}

test('groups run details by thought blocks with following commands underneath', async () => {
  const { runDetailGroups } = await modulePromise
  const groups = runDetailGroups({
    id: 'assistant-turn',
    role: 'assistant',
    sessionId: 'session',
    turnId: 'turn',
    createdAt: '2026-05-11T00:00:00.000Z',
    parts: [
      { type: 'reasoning', text: 'First thought. ' },
      { type: 'reasoning', text: 'Still first thought.' },
      tool('read-1', 'read_file'),
      tool('search-1', 'search_files'),
      { type: 'reasoning', text: 'Second thought.' },
      tool('terminal-1', 'terminal')
    ]
  })

  assert.equal(groups.length, 2)
  assert.equal(groups[0].thoughtText, 'First thought. Still first thought.')
  assert.deepEqual(groups[0].tools.map(part => part.toolCallId), ['read-1', 'search-1'])
  assert.equal(groups[1].thoughtText, 'Second thought.')
  assert.deepEqual(groups[1].tools.map(part => part.toolCallId), ['terminal-1'])
})

test('attaches thought-token fallback to the first command group', async () => {
  const { runDetailGroups } = await modulePromise
  const groups = runDetailGroups({
    id: 'assistant-turn',
    role: 'assistant',
    sessionId: 'session',
    turnId: 'turn',
    createdAt: '2026-05-11T00:00:00.000Z',
    usage: { totalTokens: 10, inputTokens: 4, outputTokens: 6, thoughtTokens: 42 },
    parts: [tool('cmd-1', 'terminal')]
  })

  assert.equal(groups.length, 1)
  assert.match(groups[0].thoughtDetail, /42 thought tokens/)
  assert.deepEqual(groups[0].tools.map(part => part.toolCallId), ['cmd-1'])
})
