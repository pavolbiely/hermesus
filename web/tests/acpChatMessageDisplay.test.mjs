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
  const sourcePath = resolve('app/utils/acpChatMessageDisplay.ts')
  const tempPath = resolve(tmpdir(), `hermesum-acpChatMessageDisplay.${process.pid}.${randomUUID()}.ts`)
  tempModules.push(tempPath)

  let source = await readFile(sourcePath, 'utf8')
  source = source.replace("import type { AcpChatMessage } from '../types/acp-chat'\n", '')
  source = source.replace("import { hasThoughtActivity } from './acpRunDetails'\n", "function hasThoughtActivity(message) { return Boolean(message.usage?.thoughtTokens) || message.parts.some(part => part.type === 'reasoning' && part.text?.trim()) }\n")
  await mkdir(dirname(tempPath), { recursive: true })
  await writeFile(tempPath, source, 'utf8')
  return import(pathToFileURL(tempPath).href)
}

function message(id, role, parts) {
  return { id, role, sessionId: 'session', turnId: id, createdAt: '2026-05-11T00:00:00.000Z', parts }
}

test('extracts text from multiple text parts', async () => {
  const { partText } = await modulePromise
  assert.equal(partText(message('m1', 'assistant', [
    { type: 'text', text: 'Hello ' },
    { type: 'reasoning', text: 'hidden' },
    { type: 'text', text: 'world' }
  ])), 'Hello world')
})

test('falls back for system event title and severity', async () => {
  const { systemEventTitle, systemEventSeverity } = await modulePromise
  const plain = message('m1', 'system', [{ type: 'text', text: 'notice' }])
  assert.equal(systemEventTitle(plain), 'System event')
  assert.equal(systemEventSeverity(plain), 'info')
})

test('reads system event title and severity from event parts', async () => {
  const { systemEventTitle, systemEventSeverity } = await modulePromise
  const event = message('m1', 'system', [{ type: 'event', title: 'Steer', severity: 'warning', body: 'Changed direction' }])
  assert.equal(systemEventTitle(event), 'Steer')
  assert.equal(systemEventSeverity(event), 'warning')
})

test('merges adjacent assistant process-only messages', async () => {
  const { groupProcessMessages } = await modulePromise
  const grouped = groupProcessMessages([
    message('a1', 'assistant', [{ type: 'reasoning', text: 'Thinking' }]),
    message('a2', 'assistant', [{ type: 'tool', toolCallId: 't1', name: 'read_file', state: 'completed' }])
  ])

  assert.equal(grouped.length, 1)
  assert.equal(grouped[0].id, 'a1:a2')
  assert.deepEqual(grouped[0].parts.map(part => part.type), ['reasoning', 'tool'])
})

test('does not merge assistant text messages', async () => {
  const { groupProcessMessages } = await modulePromise
  const grouped = groupProcessMessages([
    message('a1', 'assistant', [{ type: 'text', text: 'First' }]),
    message('a2', 'assistant', [{ type: 'reasoning', text: 'Thinking' }])
  ])

  assert.equal(grouped.length, 2)
})

test('keeps repeated identical text messages distinct', async () => {
  const { groupProcessMessages } = await modulePromise
  const grouped = groupProcessMessages([
    message('u1', 'user', [{ type: 'text', text: 'again' }]),
    message('a1', 'assistant', [{ type: 'text', text: 'again' }]),
    message('u2', 'user', [{ type: 'text', text: 'again' }])
  ])

  assert.deepEqual(grouped.map(item => item.id), ['u1', 'a1', 'u2'])
})

test('maps attachment parts to UChatMessage file parts for display', async () => {
  const { attachmentsAsFileParts } = await modulePromise
  const display = attachmentsAsFileParts(message('u1', 'user', [
    { type: 'text', text: 'see image' },
    { type: 'attachment', id: 'att1', name: 'paste.png', mediaType: 'image/png', size: 12, data: 'abc' }
  ]))

  assert.deepEqual(display.parts, [
    { type: 'text', text: 'see image' },
    { type: 'file', id: 'att1', filename: 'paste.png', mediaType: 'image/png', size: 12, url: 'data:image/png;base64,abc' }
  ])
})
