import assert from 'node:assert/strict'
import { test } from 'node:test'
import { finalizeTaskPlansInMessages } from '../app/utils/chatRunMessages.ts'
import { formatMessageGenerationDuration, formatMessageTimestamp, formatMessageTokenCount, formatProcessPartDuration, groupMessageParts, latestChangePartKey, messageDurationDetails, messagePartKey, messageText, messageTokenDetails, processGroupSummary } from '../app/utils/chatMessages.ts'

test('finalizes in-progress task plan items after the current run ends', () => {
  const messages = [
    {
      id: 'old-assistant',
      role: 'assistant',
      createdAt: '2026-01-01T09:59:00.000Z',
      parts: [{ type: 'task_plan', taskPlan: { items: [{ id: 'old', content: 'Old task', status: 'in_progress' }] } }]
    },
    {
      id: 'user',
      role: 'user',
      createdAt: '2026-01-01T10:00:00.000Z',
      parts: [{ type: 'text', text: 'Do it' }]
    },
    {
      id: 'assistant',
      role: 'assistant',
      createdAt: '2026-01-01T10:01:00.000Z',
      parts: [{
        type: 'task_plan',
        taskPlan: {
          items: [
            { id: 'done', content: 'Done', status: 'completed' },
            { id: 'active', content: 'Active', status: 'in_progress' },
            { id: 'pending', content: 'Pending', status: 'pending' }
          ]
        }
      }]
    }
  ]

  assert.equal(finalizeTaskPlansInMessages(messages, 'completed'), true)
  assert.equal(messages[0].parts[0].taskPlan.items[0].status, 'in_progress')
  assert.deepEqual(messages[2].parts[0].taskPlan.items.map(item => item.status), ['completed', 'completed', 'pending'])
  assert.match(messages[2].parts[0].taskPlan.updatedAt, /^\d{4}-\d{2}-\d{2}T/)
})

test('cancels in-progress task plan items for stopped or failed runs', () => {
  const messages = [{
    id: 'assistant',
    role: 'assistant',
    createdAt: '2026-01-01T10:01:00.000Z',
    parts: [{ type: 'task_plan', taskPlan: { items: [{ id: 'active', content: 'Active', status: 'in_progress' }] } }]
  }]

  assert.equal(finalizeTaskPlansInMessages(messages, 'cancelled'), true)
  assert.equal(messages[0].parts[0].taskPlan.items[0].status, 'cancelled')
})

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
    { type: 'event', title: 'Run stopped', eventType: 'run_stopped' },
    { type: 'steer', text: 'Please continue' }
  ])

  assert.equal(groups.length, 6)
  assert.equal(groups[0].type, 'process')
  assert.equal(groups[1].type, 'part')
  assert.equal(groups[2].type, 'part')
  assert.equal(groups[3].type, 'part')
  assert.equal(groups[4].type, 'part')
  assert.equal(groups[5].type, 'part')
})

test('groups status parts with run details', () => {
  const groups = groupMessageParts([
    { type: 'text', text: 'Before' },
    { type: 'status', text: 'Switching provider', status: 'lifecycle' },
    { type: 'tool', name: 'terminal' }
  ])

  assert.equal(groups.length, 2)
  assert.equal(groups[1].type, 'process')
  assert.equal(groups[1].parts.map(part => part.type).join(','), 'status,tool')
})

test('summarizes status and warning process parts', () => {
  assert.equal(processGroupSummary([
    { type: 'status', text: 'Switching provider', status: 'lifecycle' },
    { type: 'status', text: 'Compression failed', status: 'warn' }
  ]), '1 warning')
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

test('finds the newest git changes part across messages', () => {
  const firstChange = { type: 'changes', changes: { files: [{ path: 'old.ts' }], totalFiles: 1 } }
  const latestChange = { type: 'changes', changes: { files: [{ path: 'new.ts' }], totalFiles: 1 } }
  const messages = [
    { id: 'message-1', role: 'assistant', createdAt: '2026-01-01T10:00:00.000Z', parts: [firstChange] },
    { id: 'message-2', role: 'assistant', createdAt: '2026-01-01T10:01:00.000Z', parts: [{ type: 'text', text: 'Done' }, latestChange] }
  ]

  assert.equal(messagePartKey(messages[0], firstChange), 'message-1:0')
  assert.equal(latestChangePartKey(messages), 'message-2:1')
})

test('ignores empty git changes when finding the newest change part', () => {
  assert.equal(latestChangePartKey([
    {
      id: 'message-1',
      role: 'assistant',
      createdAt: '2026-01-01T10:00:00.000Z',
      parts: [{ type: 'changes', changes: { files: [], totalFiles: 0 } }]
    }
  ]), null)
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

test('formats message token counts', () => {
  assert.equal(formatMessageTokenCount({
    id: 'message-1',
    role: 'assistant',
    createdAt: '2026-01-01T10:00:00.000Z',
    tokenCount: 1,
    parts: []
  }), '1 token')
  assert.equal(formatMessageTokenCount({
    id: 'message-2',
    role: 'assistant',
    createdAt: '2026-01-01T10:00:00.000Z',
    tokenCount: 1234,
    parts: []
  }), '1.2K tokens')
  assert.equal(formatMessageTokenCount({
    id: 'message-3',
    role: 'assistant',
    createdAt: '2026-01-01T10:00:00.000Z',
    tokenCount: 0,
    parts: []
  }), '')
})

test('formats message token details', () => {
  assert.deepEqual(messageTokenDetails({
    id: 'message-1',
    role: 'assistant',
    createdAt: '2026-01-01T10:00:00.000Z',
    tokenCount: 1298,
    inputTokens: 1000,
    outputTokens: 200,
    cacheReadTokens: 50,
    cacheWriteTokens: 25,
    reasoningTokens: 23,
    apiCalls: 2,
    parts: []
  }), [
    { label: 'Input', value: '1K tokens' },
    { label: 'Cache read', value: '50 tokens' },
    { label: 'Cache write', value: '25 tokens' },
    { label: 'Output', value: '200 tokens' },
    { label: 'Reasoning', value: '23 tokens' },
    { label: 'API calls', value: '2' }
  ])
})

test('formats process part duration', () => {
  assert.equal(formatProcessPartDuration({
    type: 'tool',
    startedAt: '2026-01-01T10:00:00.000Z'
  }, new Date('2026-01-01T10:00:12.900Z')), '12s')

  assert.equal(formatProcessPartDuration({
    type: 'reasoning',
    durationMs: 65_000
  }), '1m 5s')

  assert.equal(formatProcessPartDuration({
    type: 'tool',
    durationMs: 500
  }), '')
})

test('formats message generation duration', () => {
  assert.equal(formatMessageGenerationDuration({
    id: 'message-1',
    role: 'assistant',
    createdAt: '2026-01-01T10:00:00.000Z',
    generationDurationMs: 1250,
    parts: []
  }), '1.3s')
  assert.equal(formatMessageGenerationDuration({
    id: 'message-2',
    role: 'assistant',
    createdAt: '2026-01-01T10:00:00.000Z',
    generationDurationMs: 72_000,
    parts: []
  }), '1m 12s')
  assert.equal(formatMessageGenerationDuration({
    id: 'message-3',
    role: 'assistant',
    createdAt: '2026-01-01T10:00:00.000Z',
    generationDurationMs: 250,
    parts: []
  }), '')
})

test('formats message duration details', () => {
  assert.deepEqual(messageDurationDetails({
    id: 'message-1',
    role: 'assistant',
    createdAt: '2026-01-01T10:00:00.000Z',
    generationDurationMs: 72_000,
    modelDurationMs: 60_000,
    toolDurationMs: 10_000,
    promptWaitDurationMs: 2_000,
    parts: []
  }), [
    { label: 'Total', value: '1m 12s' },
    { label: 'Model / orchestration', value: '1m' },
    { label: 'Tools', value: '10s' },
    { label: 'Waiting for input', value: '2s' }
  ])
})

test('formats older message timestamps with date and time', () => {
  const value = formatMessageTimestamp(
    '2026-01-01T10:30:00.000Z',
    new Date('2026-01-02T12:00:00.000Z')
  )

  assert.match(value, /Jan|1/)
})
