import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildSessionGroups } from '../app/utils/sessionGroups.ts'

const session = (overrides) => ({
  id: overrides.id,
  title: null,
  preview: '',
  source: null,
  model: null,
  reasoningEffort: null,
  workspace: overrides.workspace ?? null,
  pinned: overrides.pinned ?? false,
  archived: overrides.archived ?? false,
  messageCount: 0,
  createdAt: overrides.createdAt ?? '2026-01-01T00:00:00Z',
  updatedAt: overrides.updatedAt ?? '2026-01-01T00:00:00Z'
})

const workspace = (overrides) => ({
  id: overrides.id,
  label: overrides.label,
  path: overrides.path,
  active: overrides.active ?? false
})

test('keeps empty managed workspaces visible in configured order', () => {
  const groups = buildSessionGroups({
    sessions: [session({ id: 's1', workspace: '/repo/beta' })],
    workspaces: [
      workspace({ id: 'beta', label: 'Beta', path: '/repo/beta' }),
      workspace({ id: 'alpha', label: 'Alpha', path: '/repo/alpha' })
    ],
    selectedWorkspace: null
  })

  assert.deepEqual(groups.map(group => ({ label: group.label, sessions: group.sessions.map(s => s.id) })), [
    { label: 'Beta', sessions: ['s1'] },
    { label: 'Alpha', sessions: [] }
  ])
})

test('keeps unknown workspace chats in their workspace group instead of other chats', () => {
  const groups = buildSessionGroups({
    sessions: [session({ id: 's1', workspace: '/repo/unknown' })],
    workspaces: [workspace({ id: 'alpha', label: 'Alpha', path: '/repo/alpha' })],
    selectedWorkspace: null
  })

  assert.deepEqual(groups.map(group => ({ label: group.label, sessions: group.sessions.map(s => s.id) })), [
    { label: 'Alpha', sessions: [] },
    { label: '/repo/unknown', sessions: ['s1'] }
  ])
})

test('keeps archived chats in a separate group after other chats', () => {
  const groups = buildSessionGroups({
    sessions: [
      session({ id: 'visible', workspace: null }),
      session({ id: 'archived', workspace: '/repo/alpha', archived: true })
    ],
    workspaces: [workspace({ id: 'alpha', label: 'Alpha', path: '/repo/alpha' })],
    selectedWorkspace: null
  })

  assert.deepEqual(groups.map(group => ({ label: group.label, sessions: group.sessions.map(s => s.id) })), [
    { label: 'Alpha', sessions: [] },
    { label: 'Other chats', sessions: ['visible'] },
    { label: 'Archived', sessions: ['archived'] }
  ])
})

test('keeps pinned chats first within workspace groups', () => {
  const groups = buildSessionGroups({
    sessions: [
      session({ id: 'newer-unpinned', workspace: '/repo/alpha', updatedAt: '2026-01-04T00:00:00Z' }),
      session({ id: 'older-pinned', workspace: '/repo/alpha', pinned: true, updatedAt: '2026-01-02T00:00:00Z' }),
      session({ id: 'newer-pinned', workspace: '/repo/alpha', pinned: true, updatedAt: '2026-01-03T00:00:00Z' })
    ],
    workspaces: [workspace({ id: 'alpha', label: 'Alpha', path: '/repo/alpha' })],
    selectedWorkspace: null
  })

  assert.deepEqual(groups[0].sessions.map(s => s.id), [
    'newer-pinned',
    'older-pinned',
    'newer-unpinned'
  ])
})

test('sorts chats within workspace groups by last message time', () => {
  const groups = buildSessionGroups({
    sessions: [
      session({ id: 'older-start-newer-message', workspace: '/repo/alpha', createdAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-03T00:00:00Z' }),
      session({ id: 'newer-start-older-message', workspace: '/repo/alpha', createdAt: '2026-01-02T00:00:00Z', updatedAt: '2026-01-02T00:00:00Z' }),
      session({ id: 'other-newer-message', workspace: null, updatedAt: '2026-01-04T00:00:00Z' }),
      session({ id: 'other-older-message', workspace: '/unknown', updatedAt: '2026-01-01T00:00:00Z' })
    ],
    workspaces: [workspace({ id: 'alpha', label: 'Alpha', path: '/repo/alpha' })],
    selectedWorkspace: null
  })

  assert.deepEqual(groups[0].sessions.map(s => s.id), [
    'older-start-newer-message',
    'newer-start-older-message'
  ])
  assert.deepEqual(groups[1].sessions.map(s => s.id), [
    'other-older-message'
  ])
  assert.deepEqual(groups[2].sessions.map(s => s.id), [
    'other-newer-message'
  ])
})
