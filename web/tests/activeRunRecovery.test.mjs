import test from 'node:test'
import assert from 'node:assert/strict'
import { recoverActiveRun, reconcileActiveRunSnapshot } from '../app/utils/activeRunRecovery.ts'

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

test('clears stale local running state when session snapshot has no active run', () => {
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

test('does not clear idle sessions when session snapshot has no active run', () => {
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
