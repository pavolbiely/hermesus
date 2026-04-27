import assert from 'node:assert/strict'
import { test } from 'node:test'
import { formatCompactRelativeTime } from '../app/composables/useRelativeTime.ts'

test('formats new timestamps as 1m instead of now', () => {
  assert.equal(
    formatCompactRelativeTime('2026-01-01T10:00:00.000Z', new Date('2026-01-01T10:00:30.000Z')),
    '1m'
  )
})

test('advances relative minutes as the supplied clock advances', () => {
  const value = '2026-01-01T10:00:00.000Z'

  assert.equal(formatCompactRelativeTime(value, new Date('2026-01-01T10:01:30.000Z')), '1m')
  assert.equal(formatCompactRelativeTime(value, new Date('2026-01-01T10:05:30.000Z')), '5m')
})
