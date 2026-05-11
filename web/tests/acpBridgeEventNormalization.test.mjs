import assert from 'node:assert/strict'
import { test } from 'node:test'
import { normalizeAcpBridgeEvent } from '../app/utils/acpBridgeEventNormalization.ts'
import { applyAcpChatEvent, createEmptyAcpTranscriptState } from '../app/utils/acpEventNormalization.ts'

function text(message) {
  return message.parts.filter(part => part.type === 'text').map(part => part.text).join('')
}

test('normalizes ACP prompt and assistant chunks into one ordered turn', () => {
  let state = createEmptyAcpTranscriptState()
  const events = [
    { type: 'prompt.started', sessionId: 's1', turnId: 't1', messageId: 'u1', message: 'Say hello' },
    { type: 'session.update', sessionId: 's1', turnId: 't1', notification: { sessionId: 's1', update: { sessionUpdate: 'agent_message_chunk', messageId: 'a1', content: { type: 'text', text: 'hel' } } } },
    { type: 'session.update', sessionId: 's1', turnId: 't1', notification: { sessionId: 's1', update: { sessionUpdate: 'agent_message_chunk', messageId: 'a1', content: { type: 'text', text: 'lo' } } } },
    { type: 'prompt.completed', sessionId: 's1', turnId: 't1', messageId: 'u1', response: { stopReason: 'end_turn' } }
  ]

  for (const event of events) {
    for (const chatEvent of normalizeAcpBridgeEvent(event)) {
      state = applyAcpChatEvent(state, chatEvent)
    }
  }

  assert.deepEqual(state.messages.map(message => [message.role, message.turnId, text(message)]), [
    ['user', 't1', 'Say hello'],
    ['assistant', 't1', 'hello']
  ])
})

test('normalizes ACP tool call lifecycle without text matching', () => {
  let state = createEmptyAcpTranscriptState()
  const started = normalizeAcpBridgeEvent({
    type: 'session.update',
    sessionId: 's1',
    notification: { sessionId: 's1', update: { sessionUpdate: 'tool_call', toolCallId: 'tool-1', title: 'Read file', rawInput: { path: 'README.md' } } }
  })
  const completed = normalizeAcpBridgeEvent({
    type: 'session.update',
    sessionId: 's1',
    notification: { sessionId: 's1', update: { sessionUpdate: 'tool_call_update', toolCallId: 'tool-1', title: 'Read file', content: [{ type: 'text', text: 'done' }] } }
  })

  for (const event of [...started, ...completed]) {
    state = applyAcpChatEvent(state, event)
  }

  const tool = state.messages[0]?.parts[0]
  assert.equal(tool?.type, 'tool')
  assert.equal(tool.toolCallId, 'tool-1')
  assert.equal(tool.state, 'completed')
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
