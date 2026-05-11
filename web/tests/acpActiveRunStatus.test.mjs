import assert from 'node:assert/strict'
import { test } from 'node:test'
import { formatElapsedDuration } from '../app/composables/useAcpActiveRunStatus.ts'

test('formats active run elapsed durations compactly', () => {
  assert.equal(formatElapsedDuration(0), '0s')
  assert.equal(formatElapsedDuration(999), '0s')
  assert.equal(formatElapsedDuration(65_000), '1m 5s')
  assert.equal(formatElapsedDuration(120_000), '2m')
})
