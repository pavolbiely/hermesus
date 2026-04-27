import assert from 'node:assert/strict'
import { test } from 'node:test'
import { scrollElementTreeToBottomAfterRender } from '../app/utils/chatInitialScroll.ts'

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
