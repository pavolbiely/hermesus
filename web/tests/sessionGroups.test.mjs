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
  messageCount: 0,
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z'
})

const workspace = (overrides) => ({
  id: overrides.id,
  label: overrides.label,
  path: overrides.path,
  active: overrides.active ?? false
})

test('keeps empty managed workspaces visible and sorts them alphabetically', () => {
  const groups = buildSessionGroups({
    sessions: [session({ id: 's1', workspace: '/repo/beta' })],
    workspaces: [
      workspace({ id: 'beta', label: 'Beta', path: '/repo/beta' }),
      workspace({ id: 'alpha', label: 'Alpha', path: '/repo/alpha' })
    ],
    selectedWorkspace: null
  })

  assert.deepEqual(groups.map(group => ({ label: group.label, sessions: group.sessions.map(s => s.id) })), [
    { label: 'Alpha', sessions: [] },
    { label: 'Beta', sessions: ['s1'] }
  ])
})

test('keeps other chats after managed workspace groups', () => {
  const groups = buildSessionGroups({
    sessions: [session({ id: 's1', workspace: null })],
    workspaces: [workspace({ id: 'alpha', label: 'Alpha', path: '/repo/alpha' })],
    selectedWorkspace: null
  })

  assert.deepEqual(groups.map(group => group.label), ['Alpha', 'Other chats'])
})
