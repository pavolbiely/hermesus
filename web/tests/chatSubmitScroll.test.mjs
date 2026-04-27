import assert from 'node:assert/strict'
import { test } from 'node:test'
import { scrollElementTreeToBottomAfterRender, nearestScrollableAncestor, isElementVisibleInRoot } from '../app/utils/chatInitialScroll.ts'

test('scrolls the chat tree to bottom after the submitted message has rendered', async () => {
  const calls = []
  const page = { scrollHeight: 500, clientHeight: 100, scrollTop: 0 }
  const child = { scrollHeight: 700, clientHeight: 200, scrollTop: 0, parentElement: null }
  const parent = { scrollHeight: 900, clientHeight: 300, scrollTop: 0, parentElement: null }
  child.parentElement = parent

  const previousDocument = globalThis.document
  globalThis.document = { scrollingElement: page }

  try {
    const scrolledCount = await scrollElementTreeToBottomAfterRender(child, {
      waitForDomUpdate: async () => calls.push('dom'),
      waitForFrame: async () => calls.push('frame')
    })

    assert.deepEqual(calls, ['dom', 'frame'])
    assert.equal(scrolledCount, 3)
    assert.equal(child.scrollTop, 700)
    assert.equal(parent.scrollTop, 900)
    assert.equal(page.scrollTop, 500)
  } finally {
    globalThis.document = previousDocument
  }
})

test('can wait for multiple layout frames before scrolling to bottom', async () => {
  const calls = []
  const page = { scrollHeight: 500, clientHeight: 100, scrollTop: 0 }
  const child = { scrollHeight: 700, clientHeight: 200, scrollTop: 0, parentElement: null }
  const previousDocument = globalThis.document
  globalThis.document = { scrollingElement: page }

  try {
    await scrollElementTreeToBottomAfterRender(child, {
      waitForDomUpdate: async () => calls.push('dom'),
      waitForFrame: async () => calls.push('frame'),
      frameCount: 3
    })

    assert.deepEqual(calls, ['dom', 'frame', 'frame', 'frame'])
    assert.equal(child.scrollTop, 700)
    assert.equal(page.scrollTop, 500)
  } finally {
    globalThis.document = previousDocument
  }
})

test('finds the nearest scrollable ancestor for read receipt visibility', () => {
  const page = { scrollHeight: 500, clientHeight: 100 }
  const root = { scrollHeight: 300, clientHeight: 300, parentElement: null }
  const scrollable = { scrollHeight: 900, clientHeight: 300, parentElement: root }
  const child = { scrollHeight: 100, clientHeight: 100, parentElement: scrollable }
  const previousDocument = globalThis.document
  globalThis.document = { scrollingElement: page }

  try {
    assert.equal(nearestScrollableAncestor(child), scrollable)
  } finally {
    globalThis.document = previousDocument
  }
})

test('checks element visibility against the actual scroll root', () => {
  const previousWindow = globalThis.window
  const previousDocument = globalThis.document
  globalThis.window = { innerHeight: 800 }
  globalThis.document = { documentElement: { clientHeight: 800 } }

  try {
    const root = { getBoundingClientRect: () => ({ top: 100, bottom: 500, height: 400 }) }
    assert.equal(isElementVisibleInRoot({ getBoundingClientRect: () => ({ top: 460, bottom: 520, height: 60 }) }, root), true)
    assert.equal(isElementVisibleInRoot({ getBoundingClientRect: () => ({ top: 510, bottom: 560, height: 50 }) }, root), false)
  } finally {
    globalThis.window = previousWindow
    globalThis.document = previousDocument
  }
})
