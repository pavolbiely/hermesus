import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isAcpPlanUpdate, normalizeAcpPlanEntries } from '../app/utils/acpPlanNormalization.ts'

test('normalizes ACP plan entries as complete replacement data', () => {
  const entries = normalizeAcpPlanEntries([
    { content: ' Inspect ACP stream ', priority: 'high', status: 'completed' },
    { content: 'Render plan card', priority: 'medium', status: 'in_progress' },
    { content: 'Missing priority defaults', status: 'pending' }
  ])

  assert.deepEqual(entries, [
    { content: 'Inspect ACP stream', priority: 'high', status: 'completed' },
    { content: 'Render plan card', priority: 'medium', status: 'in_progress' },
    { content: 'Missing priority defaults', priority: 'medium', status: 'pending' }
  ])
})

test('drops invalid plan entries instead of inventing protocol states', () => {
  const entries = normalizeAcpPlanEntries([
    { content: 'Cancelled is not an ACP plan status', priority: 'low', status: 'cancelled' },
    { content: '', priority: 'high', status: 'pending' },
    { content: 'Valid item', priority: 'unknown', status: 'pending' }
  ])

  assert.deepEqual(entries, [
    { content: 'Valid item', priority: 'medium', status: 'pending' }
  ])
})

test('recognizes ACP session plan updates', () => {
  assert.equal(isAcpPlanUpdate({ sessionUpdate: 'plan', entries: [] }), true)
  assert.equal(isAcpPlanUpdate({ sessionUpdate: 'tool_call', entries: [] }), false)
})
