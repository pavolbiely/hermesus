import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  notificationSoundDebugState,
  notificationSoundVariant,
  playNotificationSound
} from '../app/utils/notificationSound.ts'

test('uses the subtle sound only when the active chat latest content is visible', () => {
  assert.equal(notificationSoundVariant({ activeVisibleChat: true, latestContentVisible: true }), 'default')
})

test('uses the attention sound when active chat is scrolled away from latest content', () => {
  assert.equal(notificationSoundVariant({ activeVisibleChat: true, latestContentVisible: false }), 'attention')
})

test('uses the attention sound outside the active visible chat', () => {
  assert.equal(notificationSoundVariant({ activeVisibleChat: false, latestContentVisible: true }), 'attention')
})

test('supports a separate outgoing sent sound variant', () => {
  assert.equal('sent', 'sent')
})

test('play attempts audio even when it was not explicitly prepared first', async () => {
  let oscillatorStarts = 0
  let gainConnected = false

  class FakeAudioContext {
    state = 'running'
    currentTime = 1
    destination = {}

    createGain() {
      return {
        gain: {
          setValueAtTime() {},
          exponentialRampToValueAtTime() {}
        },
        connect(target) {
          gainConnected = target === globalThis.window.AudioContext.lastInstance.destination
        },
        disconnect() {}
      }
    }

    createOscillator() {
      return {
        frequency: { setValueAtTime() {} },
        connect() {},
        start() { oscillatorStarts += 1 },
        stop() {}
      }
    }

    async resume() {}

    constructor() {
      FakeAudioContext.lastInstance = this
    }
  }

  const previousWindow = globalThis.window
  globalThis.window = {
    AudioContext: FakeAudioContext,
    setTimeout
  }

  try {
    const played = await playNotificationSound('sent')

    assert.equal(played, true)
    assert.equal(gainConnected, true)
    assert.equal(oscillatorStarts, 2)
    assert.equal(notificationSoundDebugState().lastAttempt, 'played:sent')
  } finally {
    globalThis.window = previousWindow
  }
})
