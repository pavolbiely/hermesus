import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { after, test } from 'node:test'

const tempModules = []
const modulePromise = loadModule()

after(async () => {
  await Promise.all(tempModules.map(path => rm(path, { recursive: true, force: true }).catch(() => undefined)))
})

async function loadModule() {
  const sourcePath = resolve('app/utils/acpRunDetailDisplay.ts')
  const tempPath = resolve(tmpdir(), `hermesum-acpRunDetailDisplay.${process.pid}.${randomUUID()}.ts`)
  tempModules.push(tempPath)

  let source = await readFile(sourcePath, 'utf8')
  source = source.replace("import type { AcpChatMessage } from '../types/acp-chat'\n", '')
  source = source.replace("import { hasThoughtActivity, reasoningText, toolParts, type AcpToolPart } from './acpRunDetails'\n", `
function hasThoughtActivity(message) { return Boolean(message.usage?.thoughtTokens) || message.parts.some(part => part.type === 'reasoning' && part.text?.trim()) }
function reasoningText(message) { return message.parts.filter(part => part.type === 'reasoning').map(part => part.text || '').join('').trim() }
function toolParts(message) { return message.parts.filter(part => part.type === 'tool') }
`)
  source = source.replace("import { toolCallTitle } from './toolCalls'\n", "function toolCallTitle(part) { return part.name || part.kind || 'tool' }\n")
  source = source.replace("import { hasTextParts, partText } from './acpChatMessageDisplay'\n", "function hasTextParts(message) { return message.parts.some(part => part.type === 'text' && part.text.trim()) }\nfunction partText(message) { return message.parts.filter(part => part.type === 'text').map(part => part.text).join('') }\n")
  await mkdir(dirname(tempPath), { recursive: true })
  await writeFile(tempPath, source, 'utf8')
  return import(pathToFileURL(tempPath).href)
}

function message(parts, extra = {}) {
  return {
    id: 'assistant-turn',
    role: 'assistant',
    sessionId: 'session',
    turnId: 'turn',
    createdAt: '2026-05-11T00:00:00.000Z',
    parts,
    ...extra
  }
}

function tool(name, extra = {}) {
  return { type: 'tool', toolCallId: name, name, state: 'completed', status: 'completed', ...extra }
}

test('summarizes thought-only run details', async () => {
  const { runDetailSummary, hasRunDetails } = await modulePromise
  const item = message([{ type: 'reasoning', text: 'Checking options.' }])
  assert.equal(hasRunDetails(item), true)
  assert.equal(runDetailSummary(item), 'Reasoned')
})

test('summarizes tool count by category', async () => {
  const { runDetailSummary } = await modulePromise
  const item = message([
    tool('read_file'),
    tool('search_files'),
    tool('terminal')
  ])
  assert.equal(runDetailSummary(item), 'read 2 files · ran 1 command · completed')
})

test('labels failed and running tools', async () => {
  const { runDetailSummary } = await modulePromise
  assert.match(runDetailSummary(message([tool('write_file', { error: 'denied', status: 'failed' })])), /1 failed/)
  assert.match(runDetailSummary(message([tool('browser', { state: 'pending', status: 'pending' })])), /1 running/)
})

test('classifies tool categories from name and kind', async () => {
  const { classifyToolPart } = await modulePromise
  assert.equal(classifyToolPart({ name: 'patch', kind: '' }), 'edit')
  assert.equal(classifyToolPart({ name: 'supabase query', kind: '' }), 'api')
  assert.equal(classifyToolPart({ name: 'unknown', kind: '' }), 'other')
})

test('reports active run labels for tools, thinking, and responding', async () => {
  const { runActivityLabel } = await modulePromise
  assert.equal(runActivityLabel(message([tool('terminal', { state: 'pending' })]), 'turn'), 'Running terminal')
  assert.equal(runActivityLabel(message([{ type: 'reasoning', text: 'Think' }]), 'turn'), 'Thinking')
  assert.equal(runActivityLabel(message([{ type: 'text', text: 'Hello' }]), 'turn'), 'Responding…')
})

test('places active run details before the assistant text only for active turn', async () => {
  const { shouldRenderRunDetailsBeforeMessage } = await modulePromise
  const item = message([{ type: 'reasoning', text: 'Think' }])
  assert.equal(shouldRenderRunDetailsBeforeMessage(item, 'turn'), true)
  assert.equal(shouldRenderRunDetailsBeforeMessage(item, 'other-turn'), false)
})

test('computes run details spacing from text/footer state', async () => {
  const { runDetailsSpacingClass } = await modulePromise
  assert.equal(runDetailsSpacingClass(message([{ type: 'text', text: 'Answer' }]), 'before'), 'mb-4')
  assert.equal(runDetailsSpacingClass(message([{ type: 'reasoning', text: 'Think' }]), 'after', true), 'mt-4')
  assert.equal(runDetailsSpacingClass(message([{ type: 'reasoning', text: 'Think' }]), 'after', false), 'mt-2')
})
