import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isPreviewablePathCandidate, LOCAL_PATH_PATTERN, normalizePreviewPathCandidate } from '../app/utils/filePreviewPaths.ts'

test('accepts common relative and absolute local file paths', () => {
  for (const path of [
    '.hermes/plans/example.md',
    'web/app/components/ChatMessageContent.vue',
    'src/foo.ts',
    'config/app.yaml',
    'notes/meeting.md',
    'some/nested/file.py',
    'whatever/custom/path/file.vue',
    'whatever/custom/path/extensionless',
    '.github/workflows/ci.yml',
    '/Users/example/project/README.md',
    './Dockerfile',
    '../docs/plan.md'
  ]) {
    assert.equal(isPreviewablePathCandidate(path), true, path)
  }
})

test('rejects urls, commands, snippets, and ambiguous bare words', () => {
  for (const value of [
    'https://example.com/file.md',
    'file:///tmp/file.md',
    'pnpm typecheck',
    'const x = 1',
    'README',
    'src',
    'EN/SK',
    'payment/provider',
    '/sales/payment-options',
    'hello.md\nthere'
  ]) {
    assert.equal(isPreviewablePathCandidate(value), false, value)
  }
})

test('normalizes wrappers and trailing punctuation', () => {
  assert.equal(normalizePreviewPathCandidate('`.hermes/plans/example.md`,'), '.hermes/plans/example.md')
  assert.equal(normalizePreviewPathCandidate('"src/foo.ts"'), 'src/foo.ts')
})

test('plain text pattern finds strong local paths without hardcoded prefixes', () => {
  const text = 'Changed config/app.yaml and whatever/custom/path/file.vue, but not pnpm typecheck or https://example.com/a.md.'
  const matches = Array.from(text.matchAll(LOCAL_PATH_PATTERN), match => normalizePreviewPathCandidate(match[1]))
  assert.deepEqual(matches, ['config/app.yaml', 'whatever/custom/path/file.vue'])
})

test('plain text pattern finds quoted local paths', () => {
  const text = 'Plan is in ".hermes/plans/2026-04-28_194818-payment-options-section.md" and should be clickable.'
  const matches = Array.from(text.matchAll(LOCAL_PATH_PATTERN), match => normalizePreviewPathCandidate(match[1]))
  assert.deepEqual(matches, ['.hermes/plans/2026-04-28_194818-payment-options-section.md'])
})
