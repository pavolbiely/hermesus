import assert from 'node:assert/strict'
import { test } from 'node:test'
import { resolveSelectedWorkspace } from '../app/utils/workspaceSelection.ts'

const workspaces = [
  { id: 'alpha', label: 'Alpha', path: '/repo/alpha', active: false },
  { id: 'beta', label: 'Beta', path: '/repo/beta', active: false }
]

test('session without workspace preserves the current workspace selection', () => {
  assert.equal(resolveSelectedWorkspace({
    workspaces,
    preferredWorkspace: null,
    persistedWorkspace: '/repo/alpha',
    currentWorkspace: '/repo/beta'
  }), '/repo/beta')
})

test('session without workspace restores persisted workspace when current selection is empty', () => {
  assert.equal(resolveSelectedWorkspace({
    workspaces,
    preferredWorkspace: null,
    persistedWorkspace: '/repo/alpha',
    currentWorkspace: null
  }), '/repo/alpha')
})

test('new chat initialization can still restore persisted workspace', () => {
  assert.equal(resolveSelectedWorkspace({
    workspaces,
    preferredWorkspace: undefined,
    persistedWorkspace: '/repo/alpha',
    currentWorkspace: null
  }), '/repo/alpha')
})

test('session workspace takes precedence when present', () => {
  assert.equal(resolveSelectedWorkspace({
    workspaces,
    preferredWorkspace: '/repo/beta',
    persistedWorkspace: '/repo/alpha',
    currentWorkspace: null
  }), '/repo/beta')
})
