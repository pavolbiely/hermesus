import assert from 'node:assert/strict'
import { test } from 'node:test'
import { fitReadAloudTextToEngine, readAloudMaxTextLength } from '../shared/readAloud/text.ts'

test('uses engine-specific read-aloud text limits', () => {
  assert.equal(readAloudMaxTextLength('edge-tts'), 12_000)
  assert.equal(readAloudMaxTextLength('elevenlabs'), 5_000)
})

test('fits long read-aloud text to the selected engine instead of rejecting it', () => {
  const result = fitReadAloudTextToEngine(` ${'a'.repeat(5_100)} `, 'elevenlabs')

  assert.equal(result.truncated, true)
  assert.equal(result.maxLength, 5_000)
  assert.equal(result.text.length, 5_000)
})

test('keeps text unchanged when it fits the selected engine', () => {
  const result = fitReadAloudTextToEngine('Readable response', 'edge-tts')

  assert.equal(result.truncated, false)
  assert.equal(result.text, 'Readable response')
})
