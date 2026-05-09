import test from 'node:test'
import assert from 'node:assert/strict'
import { shouldShowNativeActivityIndicator, shouldShowStandaloneActivityIndicator } from '../app/utils/chatActivityIndicator.ts'

const userMessage = { id: 'user-1', role: 'user', parts: [{ type: 'text', text: 'Hello' }] }
const emptyAssistantMessage = { id: 'assistant-1', role: 'assistant', parts: [] }
const assistantWithContent = { id: 'assistant-2', role: 'assistant', parts: [{ type: 'text', text: 'Hi' }] }

test('matches Nuxt UI native activity indicator visibility', () => {
  assert.equal(shouldShowNativeActivityIndicator({ status: 'submitted', messages: [userMessage] }), true)
  assert.equal(shouldShowNativeActivityIndicator({ status: 'streaming', messages: [userMessage, emptyAssistantMessage] }), true)
  assert.equal(shouldShowNativeActivityIndicator({ status: 'streaming', messages: [userMessage, assistantWithContent] }), false)
  assert.equal(shouldShowNativeActivityIndicator({ status: 'ready', messages: [userMessage] }), false)
})

test('shows standalone activity indicator only when Nuxt UI is not already rendering one', () => {
  assert.equal(shouldShowStandaloneActivityIndicator({ status: 'submitted', messages: [userMessage], showRunActivityIndicator: true }), false)
  assert.equal(shouldShowStandaloneActivityIndicator({ status: 'streaming', messages: [userMessage, emptyAssistantMessage], showRunActivityIndicator: true }), false)
  assert.equal(shouldShowStandaloneActivityIndicator({ status: 'streaming', messages: [userMessage, assistantWithContent], showRunActivityIndicator: true }), true)
  assert.equal(shouldShowStandaloneActivityIndicator({ status: 'streaming', messages: [userMessage, assistantWithContent], showRunActivityIndicator: false }), false)
})
