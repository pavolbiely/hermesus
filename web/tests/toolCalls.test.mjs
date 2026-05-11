import assert from 'node:assert/strict'
import { test } from 'node:test'
import { toolActivityFullTitle, toolActivityTitle, toolDisplayInfo, toolInputSummary, toolInputTitle, toolOutputTitle } from '../app/utils/toolCalls.ts'

test('summarizes ACP tool locations when raw input is absent', () => {
  const part = {
    name: 'Read',
    kind: 'read',
    locations: [{ path: '/Users/pavolbiely/Sites/hermesum/web/app/utils/toolCalls.ts', line: 12 }],
    output: [{ type: 'text', text: 'ok' }]
  }

  assert.equal(toolInputSummary(part), 'toolCalls.ts:12 · …/app/utils')
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

test('normalizes ACP patch titles with unknown targets', () => {
  const part = {
    name: 'patch (patch): ?',
    kind: 'edit',
    output: [{
      type: 'diff',
      path: '/Users/pavolbiely/Sites/hermesum/web/app/pages/acp/[id].vue',
      oldText: 'old',
      newText: 'new'
    }]
  }

  assert.equal(toolDisplayInfo(part).label, 'Edit file')
  assert.equal(toolDisplayInfo(part).summary, '[id].vue · …/pages/acp')
})

test('uses only the file name in active running tool labels', () => {
  const part = {
    name: 'read: /Users/pavolbiely/Sites/beesboard/.hermes/plans/2026-05-11-catalog-action-flow-refactor.md',
    kind: 'read'
  }

  assert.equal(toolActivityTitle(part), 'Read: 2026-05-11-catalog-action-flow-refactor.md')
  assert.equal(toolActivityFullTitle(part), 'Read: /Users/pavolbiely/Sites/beesboard/.hermes/plans/2026-05-11-catalog-action-flow-refactor.md')
})

test('keeps full file paths for compact summary titles', () => {
  const inputPart = {
    name: 'Read',
    kind: 'read',
    locations: [{ path: '/Users/pavolbiely/Sites/hermesum/web/app/utils/toolCalls.ts', line: 12 }]
  }
  const outputPart = {
    output: [{ type: 'diff', path: '/Users/pavolbiely/Sites/hermesum/web/app/pages/acp/[id].vue' }]
  }

  assert.equal(toolInputSummary(inputPart), 'toolCalls.ts:12 · …/app/utils')
  assert.equal(toolInputTitle(inputPart), '/Users/pavolbiely/Sites/hermesum/web/app/utils/toolCalls.ts:12')
  assert.equal(toolOutputTitle(outputPart), '/Users/pavolbiely/Sites/hermesum/web/app/pages/acp/[id].vue')
})
