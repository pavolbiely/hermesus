import test from 'node:test'
import assert from 'node:assert/strict'
import { isLiveActiveRun, isLocallyTrackedLiveActiveRun, recoverActiveRun, reconcileActiveRunSnapshot } from '../app/utils/activeRunRecovery.ts'

test('treats running and stopping session snapshots as live active runs', () => {
  assert.equal(isLiveActiveRun({ runId: 'run-1', sessionId: 'session-1', status: 'running', prompts: [] }), true)
  assert.equal(isLiveActiveRun({ runId: 'run-1', sessionId: 'session-1', status: 'stopping', prompts: [] }), true)
  assert.equal(isLiveActiveRun({ runId: 'run-1', sessionId: 'session-1', status: 'stopped', prompts: [] }), false)
  assert.equal(isLiveActiveRun(null), false)
  assert.equal(isLiveActiveRun(undefined), false)
})

test('connects active run from session detail when route query is absent', () => {
  const calls = []

  recoverActiveRun({
    sessionId: 'session-1',
    activeRun: { runId: 'run-1', sessionId: 'session-1', status: 'running', prompts: [] },
    hasConnectedRun: () => false,
    connectRun: (runId, sessionId) => calls.push({ runId, sessionId })
  })

  assert.deepEqual(calls, [{ runId: 'run-1', sessionId: 'session-1' }])
})

test('does not reconnect terminal or already connected active runs', () => {
  const calls = []

  for (const status of ['completed', 'stopped', 'failed', 'interrupted']) {
    recoverActiveRun({
      sessionId: 'session-1',
      activeRun: { runId: `run-${status}`, sessionId: 'session-1', status, prompts: [] },
      hasConnectedRun: () => false,
      connectRun: (runId, sessionId) => calls.push({ runId, sessionId })
    })
  }
  recoverActiveRun({
    sessionId: 'session-1',
    activeRun: { runId: 'run-2', sessionId: 'session-1', status: 'running', prompts: [] },
    hasConnectedRun: () => true,
    connectRun: (runId, sessionId) => calls.push({ runId, sessionId })
  })

  assert.deepEqual(calls, [])
})

test('treats a live snapshot as prompt-active only while the run is locally tracked', () => {
  const activeRun = { runId: 'run-1', sessionId: 'session-1', status: 'running', prompts: [] }

  assert.equal(isLocallyTrackedLiveActiveRun(activeRun, 'session-1', sessionId => sessionId === 'session-1'), true)
  assert.equal(isLocallyTrackedLiveActiveRun(activeRun, 'session-1', () => false), false)
  assert.equal(isLocallyTrackedLiveActiveRun({ ...activeRun, status: 'completed' }, 'session-1', () => true), false)
  assert.equal(isLocallyTrackedLiveActiveRun({ ...activeRun, sessionId: 'session-2' }, 'session-1', () => true), false)
})

test('ignores active run from another session', () => {
  const calls = []

  recoverActiveRun({
    sessionId: 'session-1',
    activeRun: { runId: 'run-1', sessionId: 'session-2', status: 'running', prompts: [] },
    hasConnectedRun: () => false,
    connectRun: (runId, sessionId) => calls.push({ runId, sessionId })
  })

  assert.deepEqual(calls, [])
})

test('does not clear local running state before a session snapshot is loaded', () => {
  const cleared = []

  reconcileActiveRunSnapshot({
    sessionId: 'session-1',
    activeRun: undefined,
    isRunning: sessionId => sessionId === 'session-1',
    clearSessionRun: sessionId => cleared.push(sessionId),
    hasConnectedRun: () => false,
    connectRun: () => assert.fail('should not connect before a snapshot is loaded')
  })

  assert.deepEqual(cleared, [])
})

test('clears stale local running state when loaded session snapshot has no active run', () => {
  const cleared = []

  reconcileActiveRunSnapshot({
    sessionId: 'session-1',
    activeRun: null,
    isRunning: sessionId => sessionId === 'session-1',
    clearSessionRun: sessionId => cleared.push(sessionId),
    hasConnectedRun: () => false,
    connectRun: () => assert.fail('should not connect a missing run')
  })

  assert.deepEqual(cleared, ['session-1'])
})

test('does not clear idle sessions when loaded session snapshot has no active run', () => {
  const cleared = []

  reconcileActiveRunSnapshot({
    sessionId: 'session-1',
    activeRun: null,
    isRunning: () => false,
    clearSessionRun: sessionId => cleared.push(sessionId),
    hasConnectedRun: () => false,
    connectRun: () => assert.fail('should not connect a missing run')
  })

  assert.deepEqual(cleared, [])
})
