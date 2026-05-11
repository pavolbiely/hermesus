import assert from 'node:assert/strict'
import { test } from 'node:test'
import { normalizeAcpBridgeEvent } from '../shared/acp/bridgeEventNormalization.ts'
import { applyAcpChatEvent, createEmptyAcpTranscriptState } from '../shared/acp/eventNormalization.ts'

function text(message) {
  return message.parts.filter(part => part.type === 'text').map(part => part.text).join('')
}

test('normalizes ACP prompt and assistant chunks into one ordered turn', () => {
  let state = createEmptyAcpTranscriptState()
  const events = [
    { type: 'prompt.started', sessionId: 's1', turnId: 't1', messageId: 'u1', message: 'Say hello' },
    { type: 'session.update', sessionId: 's1', turnId: 't1', notification: { sessionId: 's1', update: { sessionUpdate: 'agent_message_chunk', messageId: 'a1', content: { type: 'text', text: 'hel' } } } },
    { type: 'session.update', sessionId: 's1', turnId: 't1', notification: { sessionId: 's1', update: { sessionUpdate: 'agent_message_chunk', messageId: 'a1', content: { type: 'text', text: 'lo' } } } },
    { type: 'prompt.completed', sessionId: 's1', turnId: 't1', messageId: 'a1', response: { stopReason: 'end_turn', usage: { totalTokens: 9, inputTokens: 4, outputTokens: 5 } } }
  ]

  for (const event of events) {
    for (const chatEvent of normalizeAcpBridgeEvent(event)) {
      state = applyAcpChatEvent(state, chatEvent)
    }
  }

  assert.deepEqual(state.messages.map(message => [message.role, message.turnId, text(message), message.usage?.totalTokens]), [
    ['user', 't1', 'Say hello', undefined],
    ['assistant', 't1', 'hello', 9]
  ])
})

test('preserves prompt attachments on started events', () => {
  let state = createEmptyAcpTranscriptState()
  const events = normalizeAcpBridgeEvent({
    type: 'prompt.started',
    sessionId: 's1',
    turnId: 't1',
    messageId: 'u1',
    message: 'See attached',
    attachments: [{ type: 'attachment', name: 'screenshot.png', mediaType: 'image/png', data: 'abc' }]
  })

  for (const event of events) state = applyAcpChatEvent(state, event)

  assert.equal(state.messages[0].parts.some(part => part.type === 'attachment' && part.name === 'screenshot.png' && part.data === 'abc'), true)
})

test('preserves replay attachment supplements on user chunks and keeps assistant in the same turn', () => {
  let state = createEmptyAcpTranscriptState()
  const events = [
    { type: 'session.update', sessionId: 's1', sequence: 1, turnId: 't1', messageId: 'u1', userAttachments: [{ type: 'attachment', name: 'paste.png', mediaType: 'image/png', data: 'abc' }], notification: { sessionId: 's1', update: { sessionUpdate: 'user_message_chunk', content: { type: 'text', text: 'image prompt' } } } },
    { type: 'session.update', sessionId: 's1', sequence: 2, notification: { sessionId: 's1', update: { sessionUpdate: 'agent_message_chunk', content: { type: 'text', text: 'answer' } } } }
  ]

  for (const event of events) {
    for (const chatEvent of normalizeAcpBridgeEvent(event)) {
      state = applyAcpChatEvent(state, chatEvent)
    }
  }

  assert.deepEqual(state.messages.map(message => [message.role, message.turnId, text(message)]), [
    ['user', 't1', 'image prompt'],
    ['assistant', 't1', 'answer']
  ])
  assert.equal(state.messages[0].parts.some(part => part.type === 'attachment' && part.name === 'paste.png' && part.data === 'abc'), true)
})

test('normalizes ACP tool call lifecycle without text matching', () => {
  let state = createEmptyAcpTranscriptState()
  const started = normalizeAcpBridgeEvent({
    type: 'session.update',
    sessionId: 's1',
    notification: { sessionId: 's1', update: { sessionUpdate: 'tool_call', toolCallId: 'tool-1', title: 'Read file', kind: 'read', status: 'pending', locations: [{ path: 'README.md', line: 12 }], rawInput: { path: 'README.md' } } }
  })
  const progress = normalizeAcpBridgeEvent({
    type: 'session.update',
    sessionId: 's1',
    notification: { sessionId: 's1', update: { sessionUpdate: 'tool_call_update', toolCallId: 'tool-1', status: 'in_progress', content: [{ type: 'text', text: 'reading' }] } }
  })
  const completed = normalizeAcpBridgeEvent({
    type: 'session.update',
    sessionId: 's1',
    notification: { sessionId: 's1', update: { sessionUpdate: 'tool_call_update', toolCallId: 'tool-1', title: 'Read file', status: 'completed', content: [{ type: 'text', text: 'done' }] } }
  })

  for (const event of [...started, ...progress, ...completed]) {
    state = applyAcpChatEvent(state, event)
  }

  const tool = state.messages[0]?.parts[0]
  assert.equal(tool?.type, 'tool')
  assert.equal(tool.toolCallId, 'tool-1')
  assert.equal(tool.kind, 'read')
  assert.deepEqual(tool.locations, [{ path: 'README.md', line: 12 }])
  assert.equal(tool.status, 'completed')
  assert.equal(tool.state, 'completed')
})

test('preserves descriptive ACP tool titles across generic completion updates', () => {
  let state = createEmptyAcpTranscriptState()
  const events = [
    ...normalizeAcpBridgeEvent({
      type: 'session.update',
      sessionId: 's1',
      notification: { sessionId: 's1', update: { sessionUpdate: 'tool_call', toolCallId: 'tool-2', title: 'search: toolInputSummary', kind: 'search', locations: [{ path: 'web/app' }] } }
    }),
    ...normalizeAcpBridgeEvent({
      type: 'session.update',
      sessionId: 's1',
      notification: { sessionId: 's1', update: { sessionUpdate: 'tool_call_update', toolCallId: 'tool-2', kind: 'search', status: 'completed', content: [{ content: { type: 'text', text: 'done' }, type: 'content' }] } }
    })
  ]

  for (const event of events) state = applyAcpChatEvent(state, event)
  const tool = state.messages[0]?.parts[0]

  assert.equal(tool?.type, 'tool')
  assert.equal(tool.name, 'search: toolInputSummary')
})

test('normalizes permission requests with ACP option metadata', () => {
  const events = normalizeAcpBridgeEvent({
    type: 'permission.requested',
    sessionId: 's1',
    appRequestId: 'permission-1',
    request: {
      sessionId: 's1',
      toolCall: { sessionUpdate: 'tool_call', toolCallId: 'tool-1', title: 'Write file' },
      options: [
        { optionId: 'allow-once', kind: 'allow_once', name: 'Allow once' },
        { optionId: 'reject-once', kind: 'reject_once', name: 'Reject once' }
      ]
    }
  })

  assert.equal(events.length, 1)
  assert.equal(events[0].type, 'permission.requested')
  assert.equal(events[0].requestId, 'permission-1')
  assert.deepEqual(events[0].options.map(option => [option.optionId, option.kind, option.name]), [
    ['allow-once', 'allow_once', 'Allow once'],
    ['reject-once', 'reject_once', 'Reject once']
  ])
})

test('normalizes replayed user chunks and assistant chunks in order', () => {
  let state = createEmptyAcpTranscriptState()
  const events = [
    { type: 'session.update', sessionId: 's1', sequence: 1, notification: { sessionId: 's1', update: { sessionUpdate: 'user_message_chunk', messageId: 'u1', content: { type: 'text', text: 'hel' } } } },
    { type: 'session.update', sessionId: 's1', sequence: 2, notification: { sessionId: 's1', update: { sessionUpdate: 'user_message_chunk', messageId: 'u1', content: { type: 'text', text: 'lo' } } } },
    { type: 'session.update', sessionId: 's1', sequence: 3, notification: { sessionId: 's1', update: { sessionUpdate: 'agent_message_chunk', messageId: 'a1', content: { type: 'text', text: 'world' } } } }
  ]

  for (const event of events) {
    for (const chatEvent of normalizeAcpBridgeEvent(event)) {
      state = applyAcpChatEvent(state, chatEvent)
    }
  }

  assert.deepEqual(state.messages.map(message => [message.role, message.id, text(message)]), [
    ['user', 'u1', 'hello'],
    ['assistant', 'a1', 'world']
  ])
})

test('keeps legacy replay turns separate when old ACP events have no message ids', () => {
  let state = createEmptyAcpTranscriptState()
  const events = [
    { type: 'session.update', sessionId: 'legacy-session', sequence: 1, notification: { sessionId: 'legacy-session', update: { sessionUpdate: 'user_message_chunk', content: { type: 'text', text: 'first question' } } } },
    { type: 'session.update', sessionId: 'legacy-session', sequence: 2, notification: { sessionId: 'legacy-session', update: { sessionUpdate: 'agent_message_chunk', content: { type: 'text', text: 'first answer' } } } },
    { type: 'session.update', sessionId: 'legacy-session', sequence: 3, notification: { sessionId: 'legacy-session', update: { sessionUpdate: 'tool_call', toolCallId: 'tool-1', title: 'Read file' } } },
    { type: 'session.update', sessionId: 'legacy-session', sequence: 4, notification: { sessionId: 'legacy-session', update: { sessionUpdate: 'user_message_chunk', content: { type: 'text', text: 'second question' } } } },
    { type: 'session.update', sessionId: 'legacy-session', sequence: 5, notification: { sessionId: 'legacy-session', update: { sessionUpdate: 'agent_message_chunk', content: { type: 'text', text: 'second answer' } } } }
  ]

  for (const event of events) {
    for (const chatEvent of normalizeAcpBridgeEvent(event)) {
      state = applyAcpChatEvent(state, chatEvent)
    }
  }

  assert.deepEqual(state.messages.map(message => [message.role, text(message)]), [
    ['user', 'first question'],
    ['assistant', 'first answer'],
    ['user', 'second question'],
    ['assistant', 'second answer']
  ])
  assert.equal(state.messages[1].parts.some(part => part.type === 'tool' && part.toolCallId === 'tool-1'), true)
  assert.notEqual(state.messages[0].turnId, state.messages[2].turnId)
})

test('dedupes load-response events replayed again by SSE backlog using sequence ids', () => {
  let state = createEmptyAcpTranscriptState()
  const event = { type: 'session.update', sessionId: 's1', sequence: 1, notification: { sessionId: 's1', update: { sessionUpdate: 'agent_message_chunk', messageId: 'a1', content: { type: 'text', text: 'once' } } } }
  const chatEvents = normalizeAcpBridgeEvent(event)

  for (const chatEvent of [...chatEvents, ...chatEvents]) {
    state = applyAcpChatEvent(state, chatEvent)
  }

  assert.equal(state.messages.length, 1)
  assert.equal(text(state.messages[0]), 'once')
})

test('marks open tool calls completed when a run completes without tool output updates', () => {
  let state = createEmptyAcpTranscriptState()
  const events = [
    { type: 'session.update', sessionId: 's1', turnId: 't1', notification: { sessionId: 's1', update: { sessionUpdate: 'tool_call', toolCallId: 'tool-1', title: 'Search files' } } },
    { type: 'prompt.completed', sessionId: 's1', sequence: 2, turnId: 't1', response: { stopReason: 'end_turn' } }
  ]

  for (const event of events) {
    for (const chatEvent of normalizeAcpBridgeEvent(event)) {
      state = applyAcpChatEvent(state, chatEvent)
    }
  }

  const tool = state.messages[0]?.parts[0]
  assert.equal(tool?.type, 'tool')
  assert.equal(tool.state, 'completed')
})

test('sequenced prompt completion emits distinct completion and run event ids', () => {
  const events = normalizeAcpBridgeEvent({
    type: 'prompt.completed',
    sessionId: 's1',
    sequence: 9,
    turnId: 't1',
    messageId: 'a1',
    response: { stopReason: 'end_turn' }
  })

  assert.deepEqual(events.map(event => event.type), ['message.completed', 'run.completed'])
  assert.equal(new Set(events.map(event => event.eventId)).size, 2)
  assert.deepEqual(events.map(event => event.sequence), [9, 9])
})
