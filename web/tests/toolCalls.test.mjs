import assert from 'node:assert/strict'
import { test } from 'node:test'
import { toolDisplayInfo, toolInputSummary } from '../app/utils/toolCalls.ts'

test('summarizes ACP tool locations when raw input is absent', () => {
  const part = {
    name: 'Read',
    kind: 'read',
    locations: [{ path: '/Users/pavolbiely/Sites/hermesum/web/app/utils/toolCalls.ts', line: 12 }],
    output: [{ type: 'text', text: 'ok' }]
  }

  assert.equal(toolInputSummary(part), '~/Sites/hermesum/web/app/utils/toolCalls.ts:12')
})

test('prefers explicit command input over generic output counts', () => {
  const part = {
    name: 'Execute',
    kind: 'execute',
    input: { command: 'pnpm typecheck', workdir: '/Users/pavolbiely/Sites/hermesum/web' },
    output: [{ type: 'text', text: 'done' }]
  }

  assert.equal(toolDisplayInfo(part).summary, 'pnpm typecheck')
})

test('splits ACP title labels from title detail summaries', () => {
  const part = {
    name: 'terminal: pwd',
    kind: 'execute',
    output: [{ type: 'text', text: 'done' }]
  }

  assert.equal(toolDisplayInfo(part).label, 'Terminal')
  assert.equal(toolDisplayInfo(part).summary, 'pwd')
})

test('summarizes search patterns from raw input', () => {
  const part = {
    name: 'Search',
    kind: 'search',
    input: { pattern: 'tool_call_update', path: 'web/app' },
    output: [{ type: 'text', text: 'done' }]
  }

  assert.equal(toolInputSummary(part), 'tool_call_update')
})
