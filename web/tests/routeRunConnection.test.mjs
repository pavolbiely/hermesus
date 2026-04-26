import assert from 'node:assert/strict'
import { test } from 'node:test'
import { connectRouteRun } from '../app/utils/routeRunConnection.ts'

test('connects a run id from the route query for the current session', () => {
  const connected = []

  connectRouteRun({
    sessionId: 'session-1',
    queryRun: 'run-1',
    hasConnectedRun: () => false,
    connectRun: (runId, sessionId) => connected.push({ runId, sessionId })
  })

  assert.deepEqual(connected, [{ runId: 'run-1', sessionId: 'session-1' }])
})

test('does not reconnect a route run that is already connected', () => {
  const connected = []

  connectRouteRun({
    sessionId: 'session-1',
    queryRun: 'run-1',
    hasConnectedRun: () => true,
    connectRun: (runId, sessionId) => connected.push({ runId, sessionId })
  })

  assert.deepEqual(connected, [])
})

test('ignores non-string route run values', () => {
  const connected = []

  connectRouteRun({
    sessionId: 'session-1',
    queryRun: ['run-1'],
    hasConnectedRun: () => false,
    connectRun: (runId, sessionId) => connected.push({ runId, sessionId })
  })

  assert.deepEqual(connected, [])
})
