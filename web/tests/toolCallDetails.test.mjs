import assert from 'node:assert/strict'
import { test } from 'node:test'
import { toolDetailSections, valueSummary } from '../app/utils/toolCallDetails.ts'

test('builds detail sections for present input and output payloads', () => {
  const sections = toolDetailSections({
    input: { command: 'pnpm typecheck' },
    output: '{"ok":true}'
  })

  assert.deepEqual(sections.map(section => section.label), ['Input', 'Output'])
  assert.equal(sections[0].type, 'object')
  assert.equal(sections[1].type, 'object')
  assert.equal(sections[1].text, '{\n  "ok": true\n}')
})

test('omits empty detail payloads', () => {
  const sections = toolDetailSections({
    input: '',
    output: null
  })

  assert.equal(sections.length, 0)
})

test('summarizes common structured payload counts', () => {
  assert.equal(valueSummary({ total_count: 8, files: ['a.ts', 'b.ts'] }), '8 total · 2 files')
  assert.equal(valueSummary(['one', 'two', 'three']), '3 items')
})
