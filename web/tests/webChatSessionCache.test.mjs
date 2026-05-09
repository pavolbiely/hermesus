import assert from 'node:assert/strict'
import { test } from 'node:test'

const states = new Map()
globalThis.useState = (key, init) => {
  if (!states.has(key)) states.set(key, { value: init() })
  return states.get(key)
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((innerResolve, innerReject) => {
    resolve = innerResolve
    reject = innerReject
  })
  return { promise, resolve, reject }
}

function sessionResponse(id, marker) {
  return {
    session: { id, title: marker },
    messages: [],
    activeRun: null
  }
}

test('invalidated in-flight session snapshots refetch instead of overwriting newer state', async () => {
  states.clear()
  const first = deferred()
  const second = deferred()
  const calls = []
  const api = {
    getSession(sessionId, options) {
      calls.push({ sessionId, options })
      return calls.length === 1 ? first.promise : second.promise
    }
  }
  const { useWebChatSessionCache } = await import('../app/composables/useWebChatSessionCache.ts')
  const cache = useWebChatSessionCache(api)

  const staleFetch = cache.fetch('session-1', { messageLimit: 60 })
  cache.invalidate('session-1')
  const freshFetch = cache.fetch('session-1', { messageLimit: 60 })

  first.resolve(sessionResponse('session-1', 'stale'))
  second.resolve(sessionResponse('session-1', 'fresh'))

  assert.equal((await staleFetch).session.title, 'fresh')
  assert.equal((await freshFetch).session.title, 'fresh')
  assert.equal(cache.get('session-1')?.session.title, 'fresh')
  assert.equal(calls.length, 2)
})
