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
