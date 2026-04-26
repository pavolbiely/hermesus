import assert from 'node:assert/strict'
import { test } from 'node:test'
import { formatMessageTimestamp, groupMessageParts, messageText } from '../app/utils/chatMessages.ts'

test('groups consecutive tool parts together', () => {
  const groups = groupMessageParts([
    { type: 'text', text: 'Before' },
    { type: 'tool', name: 'read_file' },
    { type: 'tool', name: 'search_files' },
    { type: 'text', text: 'After' }
  ])

  assert.equal(groups.length, 3)
  assert.equal(groups[1].type, 'tools')
  assert.equal(groups[1].parts.length, 2)
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
