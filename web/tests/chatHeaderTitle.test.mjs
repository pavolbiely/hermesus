import assert from 'node:assert/strict'
import { test } from 'node:test'
import { resolveChatHeaderTitle } from '../app/utils/chatHeaderTitle.ts'

function session(overrides = {}) {
  return {
    id: overrides.id || 'session-1',
    title: overrides.title ?? 'Original title',
    preview: overrides.preview ?? 'Preview text'
  }
}

test('uses successful local rename override for the active chat header title', () => {
  assert.equal(
    resolveChatHeaderTitle({
      isLoadingSession: false,
      sessionError: null,
      hasSession: true,
      session: session({ title: 'Original title' }),
      titleOverride: 'Renamed title'
    }),
    'Renamed title'
  )
})

test('falls back to session title, preview, and loading/error labels', () => {
  assert.equal(resolveChatHeaderTitle({ isLoadingSession: true, sessionError: null, hasSession: true, session: session() }), 'Loading chat…')
  assert.equal(resolveChatHeaderTitle({ isLoadingSession: false, sessionError: new Error('missing'), hasSession: true, session: session() }), 'Chat unavailable')
  assert.equal(resolveChatHeaderTitle({ isLoadingSession: false, sessionError: null, hasSession: false, session: null }), 'Chat unavailable')
  assert.equal(resolveChatHeaderTitle({ isLoadingSession: false, sessionError: null, hasSession: true, session: session({ title: '', preview: 'Preview title' }) }), 'Preview title')
  assert.equal(resolveChatHeaderTitle({ isLoadingSession: false, sessionError: null, hasSession: true, session: session({ title: '', preview: '' }) }), 'Chat')
})
