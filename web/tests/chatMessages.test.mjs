import assert from 'node:assert/strict'
import { test } from 'node:test'
import { formatMessageTimestamp, groupMessageParts, messageText, processGroupSummary } from '../app/utils/chatMessages.ts'

test('groups consecutive process parts together', () => {
  const groups = groupMessageParts([
    { type: 'text', text: 'Before' },
    { type: 'reasoning', text: 'Thinking' },
    { type: 'tool', name: 'read_file' },
    { type: 'tool', name: 'terminal' },
    { type: 'text', text: 'After' }
  ])

  assert.equal(groups.length, 3)
  assert.equal(groups[1].type, 'process')
  assert.equal(groups[1].parts.length, 3)
})

test('keeps non-process parts out of process groups', () => {
  const groups = groupMessageParts([
    { type: 'tool', name: 'terminal' },
    { type: 'media', attachments: [] },
    { type: 'interactive_prompt', prompt: null },
    { type: 'changes', changes: null },
    { type: 'steer', text: 'Please continue' }
  ])

  assert.equal(groups.length, 5)
  assert.equal(groups[0].type, 'process')
  assert.equal(groups[1].type, 'part')
  assert.equal(groups[2].type, 'part')
  assert.equal(groups[3].type, 'part')
  assert.equal(groups[4].type, 'part')
})

test('summarizes process groups by useful categories', () => {
  assert.equal(processGroupSummary([
    { type: 'reasoning', text: 'Thinking' },
    { type: 'tool', name: 'read_file', status: 'completed' },
    { type: 'tool', name: 'search_files', status: 'completed' },
    { type: 'tool', name: 'patch', status: 'completed' },
    { type: 'tool', name: 'terminal', status: 'completed', output: { exit_code: 0 } }
  ]), 'Reasoned · read 2 files · edited 1 file · ran 1 command · completed')
})

test('summarizes failed process groups', () => {
  assert.equal(processGroupSummary([
    { type: 'tool', name: 'terminal', status: 'completed', output: { exit_code: 1 } }
  ]), 'ran 1 command · 1 failed')
})

test('summarizes unknown process tools with fallback action count', () => {
  assert.equal(processGroupSummary([
    { type: 'tool', name: 'custom_tool', status: 'completed' },
    { type: 'tool', name: 'another_tool', status: 'completed' }
  ]), '2 actions · completed')
})

test('joins only text message parts with blank lines', () => {
  assert.equal(messageText({
    id: 'message-1',
    role: 'user',
    createdAt: '2026-01-01T10:00:00.000Z',
    parts: [
      { type: 'text', text: 'First' },
      { type: 'tool', name: 'terminal' },
      { type: 'text', text: 'Second' }
    ]
  }), 'First\n\nSecond')
})

test('formats older message timestamps with date and time', () => {
  const value = formatMessageTimestamp(
    '2026-01-01T10:30:00.000Z',
    new Date('2026-01-02T12:00:00.000Z')
  )

  assert.match(value, /Jan|1/)
})
