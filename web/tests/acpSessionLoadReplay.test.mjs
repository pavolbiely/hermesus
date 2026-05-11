import assert from 'node:assert/strict'
import { test } from 'node:test'
import { normalizeAcpBridgeEvent } from '../shared/acp/bridgeEventNormalization.ts'
import { applyAcpChatEvent, createEmptyAcpTranscriptState } from '../shared/acp/eventNormalization.ts'
import { supplementMissingTranscriptEvents } from '../server/acp/sessionReplaySupplement.ts'

function text(message) {
  return message.parts.filter(part => part.type === 'text').map(part => part.text).join('')
}

function replayEvent(sessionId, sequence, role, text, turnId = 'replayed-turn') {
  return {
    type: 'session.update',
    sessionId,
    turnId,
    sequence,
    notification: {
      sessionId,
      update: {
        sessionUpdate: role === 'user' ? 'user_message_chunk' : 'agent_message_chunk',
        content: { type: 'text', text }
      }
    }
  }
}

test('supplements raw user messages that ACP replay missed after replay failure', () => {
  const sessionId = 'session-1'
  const replayedEvents = [
    replayEvent(sessionId, 10, 'user', 'First prompt', 'turn-1'),
    replayEvent(sessionId, 11, 'assistant', 'First answer', 'turn-1')
  ]
  const supplementalEvents = supplementMissingTranscriptEvents(sessionId, [
    { role: 'user', content: 'First prompt' },
    { role: 'assistant', content: 'First answer' },
    { role: 'user', content: 'Second prompt' },
    { role: 'assistant', content: 'Second answer' },
    { role: 'user', content: [{ type: 'text', text: 'Prompt with screenshot' }, { type: 'image_url', image_url: { url: 'data:image/png;base64,abc' } }] }
  ], replayedEvents)

  assert.deepEqual(supplementalEvents.map(event => [event.sequence, event.turnId, event.notification.update.sessionUpdate, event.notification.update.content.text]), [
    [12, `${sessionId}:raw-replay-turn:2`, 'user_message_chunk', 'Second prompt'],
    [13, `${sessionId}:raw-replay-turn:4`, 'user_message_chunk', 'Prompt with screenshot']
  ])

  let state = createEmptyAcpTranscriptState()
  for (const bridgeEvent of [...replayedEvents, ...supplementalEvents]) {
    for (const event of normalizeAcpBridgeEvent(bridgeEvent)) {
      state = applyAcpChatEvent(state, event)
    }
  }

  assert.deepEqual(state.messages.map(message => [message.role, message.turnId, text(message)]), [
    ['user', 'turn-1', 'First prompt'],
    ['assistant', 'turn-1', 'First answer'],
    ['user', `${sessionId}:raw-replay-turn:2`, 'Second prompt'],
    ['user', `${sessionId}:raw-replay-turn:4`, 'Prompt with screenshot']
  ])
})
