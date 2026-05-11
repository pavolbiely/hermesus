import assert from 'node:assert/strict'
import { test } from 'node:test'
import { normalizeAcpBridgeEvent } from '../shared/acp/bridgeEventNormalization.ts'
import { applyAcpChatEvent, createEmptyAcpTranscriptState, createAcpTurnContext } from '../shared/acp/eventNormalization.ts'

function text(message) {
  return message.parts.filter(part => part.type === 'text').map(part => part.text).join('')
}

test('repeated identical prompts remain separate turns', () => {
  const first = createAcpTurnContext('session-1', 'turn-1', '2026-05-11T00:00:00.000Z')
  const second = createAcpTurnContext('session-1', 'turn-2', '2026-05-11T00:01:00.000Z')
  let state = createEmptyAcpTranscriptState()

  state = applyAcpChatEvent(state, { type: 'user.message', sessionId: first.sessionId, turnId: first.turnId, text: 'Say OK', occurredAt: first.createdAt })
  state = applyAcpChatEvent(state, { type: 'message.delta', sessionId: first.sessionId, turnId: first.turnId, text: 'OK' })
  state = applyAcpChatEvent(state, { type: 'user.message', sessionId: second.sessionId, turnId: second.turnId, text: 'Say OK', occurredAt: second.createdAt })
  state = applyAcpChatEvent(state, { type: 'message.delta', sessionId: second.sessionId, turnId: second.turnId, text: 'OK' })

  assert.deepEqual(state.messages.map(message => [message.role, message.turnId, text(message)]), [
    ['user', 'turn-1', 'Say OK'],
    ['assistant', 'turn-1', 'OK'],
    ['user', 'turn-2', 'Say OK'],
    ['assistant', 'turn-2', 'OK']
  ])
})

test('late assistant chunks stay with their matching older user turn', () => {
  let state = createEmptyAcpTranscriptState()

  state = applyAcpChatEvent(state, { type: 'user.message', sessionId: 'session-1', turnId: 'old-turn', text: 'Old prompt' })
  state = applyAcpChatEvent(state, { type: 'user.message', sessionId: 'session-1', turnId: 'new-turn', text: 'New prompt' })
  state = applyAcpChatEvent(state, { type: 'message.delta', sessionId: 'session-1', turnId: 'old-turn', text: 'Old answer' })

  assert.deepEqual(state.messages.map(message => [message.role, message.turnId, text(message)]), [
    ['user', 'old-turn', 'Old prompt'],
    ['assistant', 'old-turn', 'Old answer'],
    ['user', 'new-turn', 'New prompt']
  ])
})

test('editing a prior user message truncates the visible branch before inserting the edited prompt', () => {
  let state = createEmptyAcpTranscriptState()

  state = applyAcpChatEvent(state, { type: 'user.message', sessionId: 'session-1', turnId: 'turn-1', messageId: 'user-1', text: 'First prompt' })
  state = applyAcpChatEvent(state, { type: 'message.delta', sessionId: 'session-1', turnId: 'turn-1', text: 'First answer' })
  state = applyAcpChatEvent(state, { type: 'user.message', sessionId: 'session-1', turnId: 'turn-2', messageId: 'user-2', text: 'Second prompt' })
  state = applyAcpChatEvent(state, { type: 'message.delta', sessionId: 'session-1', turnId: 'turn-2', text: 'Second answer' })

  state = applyAcpChatEvent(state, { type: 'transcript.truncated', sessionId: 'session-1', messageId: 'user-1' })
  state = applyAcpChatEvent(state, { type: 'user.message', sessionId: 'session-1', turnId: 'turn-3', messageId: 'user-3', text: 'Edited first prompt' })

  assert.deepEqual(state.messages.map(message => [message.role, message.turnId, text(message)]), [
    ['user', 'turn-3', 'Edited first prompt']
  ])
})

test('optimistic user messages retain attachment parts', () => {
  let state = createEmptyAcpTranscriptState()

  state = applyAcpChatEvent(state, {
    type: 'user.message',
    sessionId: 'session-1',
    turnId: 'turn-1',
    messageId: 'user-1',
    text: 'See photo',
    attachments: [{
      type: 'attachment',
      id: 'att-1',
      name: 'photo.png',
      mediaType: 'image/png',
      size: 12,
      data: 'aGVsbG8='
    }]
  })

  assert.deepEqual(state.messages[0].parts.map(part => part.type), ['text', 'attachment'])
  assert.equal(state.messages[0].parts[1].name, 'photo.png')
})

test('server truncate bridge event removes edited branch and accepts following prompt events', () => {
  let state = createEmptyAcpTranscriptState()

  state = applyAcpChatEvent(state, {
    type: 'transcript.loaded',
    sessionId: 'session-1',
    cursor: 10,
    messages: [
      { id: 'user-1', role: 'user', sessionId: 'session-1', turnId: 'turn-1', createdAt: '2026-01-01T00:00:00.000Z', parts: [{ type: 'text', text: 'Old prompt' }] },
      { id: 'assistant-1', role: 'assistant', sessionId: 'session-1', turnId: 'turn-1', createdAt: '2026-01-01T00:00:01.000Z', parts: [{ type: 'text', text: 'Old answer' }] }
    ]
  })

  for (const event of normalizeAcpBridgeEvent({ type: 'transcript.truncated', sessionId: 'session-1', sequence: 11, messageId: 'user-1' })) {
    state = applyAcpChatEvent(state, event)
  }
  for (const event of normalizeAcpBridgeEvent({ type: 'prompt.started', sessionId: 'session-1', sequence: 12, turnId: 'turn-2', messageId: 'user-2', message: 'Edited prompt' })) {
    state = applyAcpChatEvent(state, event)
  }
  for (const event of normalizeAcpBridgeEvent({
    type: 'session.update',
    sessionId: 'session-1',
    sequence: 13,
    turnId: 'turn-2',
    messageId: 'user-2',
    notification: { sessionId: 'session-1', update: { sessionUpdate: 'agent_message_chunk', content: { type: 'text', text: 'New answer' } } }
  })) {
    state = applyAcpChatEvent(state, event)
  }

  assert.deepEqual(state.messages.map(message => [message.role, message.turnId, text(message)]), [
    ['user', 'turn-2', 'Edited prompt'],
    ['assistant', 'turn-2', 'New answer']
  ])
})

test('snapshot cursor prevents replay-before-sse duplicates', () => {
  let state = createEmptyAcpTranscriptState()
  state = applyAcpChatEvent(state, {
    type: 'transcript.loaded',
    sessionId: 'session-1',
    cursor: 10,
    messages: [{
      id: 'assistant-1',
      role: 'assistant',
      sessionId: 'session-1',
      turnId: 'turn-1',
      createdAt: '2026-05-11T00:00:00.000Z',
      parts: [{ type: 'text', text: 'Already loaded' }]
    }]
  })

  state = applyAcpChatEvent(state, {
    type: 'message.delta',
    sessionId: 'session-1',
    turnId: 'turn-1',
    sequence: 9,
    text: 'Already loaded'
  })

  assert.equal(state.messages.length, 1)
  assert.equal(text(state.messages[0]), 'Already loaded')
})

test('completion adopts the matching turn message id without touching newer assistant', () => {
  let state = createEmptyAcpTranscriptState()
  state = applyAcpChatEvent(state, { type: 'message.delta', sessionId: 'session-1', turnId: 'turn-1', text: 'OK' })
  state = applyAcpChatEvent(state, { type: 'message.delta', sessionId: 'session-1', turnId: 'turn-2', text: 'OK' })
  state = applyAcpChatEvent(state, {
    type: 'message.completed',
    sessionId: 'session-1',
    turnId: 'turn-1',
    messageId: 'server-assistant-1',
    occurredAt: '2026-05-11T00:00:03.000Z',
    usage: { totalTokens: 12, inputTokens: 5, outputTokens: 7 }
  })

  assert.deepEqual(state.messages.map(message => [message.id, message.turnId, text(message), message.completedAt, message.usage?.totalTokens]), [
    ['server-assistant-1', 'turn-1', 'OK', '2026-05-11T00:00:03.000Z', 12],
    ['assistant-turn-2', 'turn-2', 'OK', undefined, undefined]
  ])
})

test('replayed completion metadata attaches by user message id when turn ids differ', () => {
  let state = createEmptyAcpTranscriptState()
  state = applyAcpChatEvent(state, { type: 'user.message.delta', sessionId: 'session-1', turnId: 'user-message-1', messageId: 'user-message-1', text: 'Old prompt' })
  state = applyAcpChatEvent(state, { type: 'message.delta', sessionId: 'session-1', turnId: 'assistant-message-1', messageId: 'assistant-message-1', text: 'Old answer' })
  state = applyAcpChatEvent(state, {
    type: 'message.completed',
    sessionId: 'session-1',
    turnId: 'original-live-turn-id',
    userMessageId: 'user-message-1',
    occurredAt: '2026-05-11T00:00:03.000Z',
    usage: { totalTokens: 12, inputTokens: 5, outputTokens: 7 }
  })

  assert.deepEqual(state.messages.map(message => [message.id, message.turnId, text(message), message.completedAt, message.usage?.totalTokens]), [
    ['user-message-1', 'user-message-1', 'Old prompt', undefined, undefined],
    ['assistant-message-1', 'assistant-message-1', 'Old answer', '2026-05-11T00:00:03.000Z', 12]
  ])
})

test('event ids dedupe repeated live events', () => {
  let state = createEmptyAcpTranscriptState()
  const event = { type: 'message.delta', eventId: 'event-1', sessionId: 'session-1', turnId: 'turn-1', text: 'Hello' }

  state = applyAcpChatEvent(state, event)
  state = applyAcpChatEvent(state, event)

  assert.equal(text(state.messages[0]), 'Hello')
})
