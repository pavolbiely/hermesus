import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createRunEventReplay } from '../app/utils/runEventReplay.ts'

test('replays prompt events that arrive before a subscriber is attached', () => {
  const replay = createRunEventReplay()
  const prompt = { id: 'prompt-1', kind: 'approval', status: 'pending' }

  replay.record('onPromptRequested', prompt)

  const received = []
  replay.replay({
    onPromptRequested: value => received.push(value)
  })

  assert.deepEqual(received, [prompt])
})

test('replays assistant stream events in original order', () => {
  const replay = createRunEventReplay()
  replay.record('onToolStarted', { name: 'terminal' })
  replay.record('onDelta', 'Hello')
  replay.record('onDelta', ' world')
  replay.record('onToolCompleted', { name: 'terminal' })

  const received = []
  replay.replay({
    onToolStarted: value => received.push(['started', value.name]),
    onDelta: value => received.push(['delta', value]),
    onToolCompleted: value => received.push(['completed', value.name])
  })

  assert.deepEqual(received, [
    ['started', 'terminal'],
    ['delta', 'Hello'],
    ['delta', ' world'],
    ['completed', 'terminal']
  ])
})
