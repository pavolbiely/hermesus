import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  rememberChatComposerSelection,
  resolveSessionComposerSelection
} from '../app/utils/chatComposerSelections.ts'

test('stores model selections under isolated session ids', () => {
  let selections = {}

  selections = rememberChatComposerSelection(selections, 'session-a', {
    model: 'gpt-5.5',
    provider: 'openai-codex',
    reasoningEffort: 'high'
  })
  selections = rememberChatComposerSelection(selections, 'session-b', {
    model: 'grok-4',
    provider: 'xai',
    reasoningEffort: 'low'
  })

  assert.deepEqual(selections['session-a'], {
    model: 'gpt-5.5',
    provider: 'openai-codex',
    reasoningEffort: 'high'
  })
  assert.deepEqual(selections['session-b'], {
    model: 'grok-4',
    provider: 'xai',
    reasoningEffort: 'low'
  })
})

test('prefers saved selection for a session over globally last used values', () => {
  const saved = {
    model: 'gpt-5.5',
    provider: 'openai-codex',
    reasoningEffort: 'high'
  }
  const session = {
    model: 'grok-4',
    provider: 'xai',
    reasoningEffort: 'low'
  }

  assert.deepEqual(resolveSessionComposerSelection(session, saved), saved)
})

test('falls back only to persisted session selection when no saved selection exists', () => {
  const session = {
    model: 'gpt-5.5',
    provider: 'openai-codex',
    reasoningEffort: 'medium'
  }

  assert.deepEqual(resolveSessionComposerSelection(session), session)
})

test('does not write selections for empty session ids', () => {
  const selections = rememberChatComposerSelection({}, '', {
    model: 'gpt-5.5',
    provider: 'openai-codex',
    reasoningEffort: 'high'
  })

  assert.deepEqual(selections, {})
})
