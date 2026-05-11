import assert from 'node:assert/strict'
import { test } from 'node:test'
import { acpSidebarSessions } from '../app/utils/acpSidebarSessions.ts'

test('maps ACP session/list results to sidebar sessions', () => {
  const sessions = acpSidebarSessions({
    sessions: [
      {
        sessionId: 'session-1',
        cwd: '/repo',
        title: '  Build sidebar  ',
        updatedAt: '2026-05-11T01:00:00.000Z'
      }
    ]
  })

  assert.deepEqual(sessions, [{
    id: 'session-1',
    title: 'Build sidebar',
    preview: 'Build sidebar',
    source: 'acp',
    model: null,
    provider: null,
    reasoningEffort: null,
    workspace: '/repo',
    pinned: false,
    archived: false,
    running: false,
    messageCount: 0,
    createdAt: '2026-05-11T01:00:00.000Z',
    updatedAt: '2026-05-11T01:00:00.000Z'
  }])
})

test('falls back to ACP chat title and generated timestamp', () => {
  const sessions = acpSidebarSessions({
    sessions: [{ sessionId: 'session-2', cwd: '/repo', title: '   ', updatedAt: null }]
  })

  assert.equal(sessions[0].title, null)
  assert.equal(sessions[0].preview, 'ACP chat')
  assert.equal(sessions[0].createdAt, sessions[0].updatedAt)
  assert.ok(!Number.isNaN(new Date(sessions[0].updatedAt).getTime()))
})

test('applies app-owned ACP sidebar metadata', () => {
  const sessions = acpSidebarSessions({
    sessions: [
      {
        sessionId: 'session-3',
        cwd: '/repo',
        title: 'Runtime title',
        updatedAt: '2026-05-11T01:00:00.000Z',
        appMetadata: {
          title: 'Pinned app title',
          pinned: true,
          archived: true,
          workspace: '/workspace'
        }
      }
    ]
  })

  assert.equal(sessions[0].title, 'Pinned app title')
  assert.equal(sessions[0].preview, 'Pinned app title')
  assert.equal(sessions[0].workspace, '/workspace')
  assert.equal(sessions[0].pinned, true)
  assert.equal(sessions[0].archived, true)
})

test('marks sessions with active ACP prompts as running', () => {
  const sessions = acpSidebarSessions({
    sessions: [
      {
        sessionId: 'session-4',
        cwd: '/repo',
        title: 'Running chat',
        updatedAt: '2026-05-11T01:00:00.000Z',
        appActivePrompt: { turnId: 'turn-1', messageId: 'message-1' }
      }
    ]
  })

  assert.equal(sessions[0].running, true)
})


test('collapses compression lineage sessions under the live tip with the root title', () => {
  const sessions = acpSidebarSessions({
    sessions: [
      {
        sessionId: 'root-session',
        cwd: '/repo',
        title: 'UI zaseknuté na Starting',
        updatedAt: '2026-05-11T01:00:00.000Z',
        appLineage: { rootSessionId: 'root-session', rootTitle: 'UI zaseknuté na Starting' }
      },
      {
        sessionId: 'tip-session',
        cwd: '/repo',
        title: 'UI zaseknuté na Starting #2',
        updatedAt: '2026-05-11T02:00:00.000Z',
        appLineage: { rootSessionId: 'root-session', rootTitle: 'UI zaseknuté na Starting' }
      }
    ]
  })

  assert.equal(sessions.length, 1)
  assert.equal(sessions[0].id, 'tip-session')
  assert.equal(sessions[0].title, 'UI zaseknuté na Starting')
})
