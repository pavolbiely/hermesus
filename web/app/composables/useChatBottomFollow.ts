import { nextTick, onBeforeUnmount, onMounted, watch } from 'vue'
import type { Ref } from 'vue'
import { nearestScrollableAncestor, scrollElementTreeToBottom, scrollElementTreeToBottomAfterRender } from '~/utils/chatInitialScroll'

type ChatBottomFollowOptions = {
  scrollContainer: Ref<HTMLElement | null>
  contentContainer: Ref<HTMLElement | null>
  active: Ref<boolean>
  thresholdPx?: number
  waitForFrame?: () => Promise<void> | void
}

type ScrollAfterRenderOptions = {
  isCurrent?: () => boolean
  stableFrameCount?: number
  maxFrameCount?: number
}

export function useChatBottomFollow(options: ChatBottomFollowOptions) {
  const thresholdPx = options.thresholdPx ?? 120
  let observer: MutationObserver | undefined
  let followFrame: number | undefined
  let lastScrollTop = 0
  let userPaused = false

  function scrollRoot() {
    if (!import.meta.client) return null
    return nearestScrollableAncestor(options.scrollContainer.value) as HTMLElement | null
  }

  function distanceFromBottom(root = scrollRoot()) {
    if (!root) return 0
    return Math.max(0, root.scrollHeight - root.clientHeight - root.scrollTop)
  }

  function updateSnapshot() {
    const root = scrollRoot()
    if (root) lastScrollTop = root.scrollTop
  }

  function resetPause() {
    userPaused = false
  }

  function onScroll() {
    const root = scrollRoot()
    if (!root) return

    const distance = distanceFromBottom(root)
    const scrolledUp = root.scrollTop < lastScrollTop
    if (scrolledUp && distance > thresholdPx) {
      userPaused = true
    } else if (distance <= thresholdPx) {
      userPaused = false
    }
    lastScrollTop = root.scrollTop
  }

  function followToBottom() {
    if (!options.active.value || userPaused) return
    scheduleFollowScroll()
  }

  function scheduleFollowScroll() {
    if (!import.meta.client) return
    if (followFrame) cancelAnimationFrame(followFrame)

    followFrame = requestAnimationFrame(() => {
      followFrame = undefined
      const root = scrollRoot()
      if (!root || userPaused) return

      root.scrollTo({
        top: root.scrollHeight,
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
      })
      lastScrollTop = root.scrollTop
    })
  }

  function setupObserver() {
    if (!import.meta.client || observer || !options.contentContainer.value) return
    observer = new MutationObserver(() => followToBottom())
    observer.observe(options.contentContainer.value, {
      childList: true,
      characterData: true,
      subtree: true
    })
  }

  function teardownObserver() {
    observer?.disconnect()
    observer = undefined
    if (followFrame) cancelAnimationFrame(followFrame)
    followFrame = undefined
  }

  async function scrollToBottomAfterRender(scrollOptions: ScrollAfterRenderOptions = {}) {
    if (!import.meta.client) return

    resetPause()
    await nextTick()
    if (scrollOptions.isCurrent?.() === false) return

    scrollElementTreeToBottom(options.scrollContainer.value)
    await scrollElementTreeToBottomAfterRender(options.scrollContainer.value, {
      waitForFrame: options.waitForFrame,
      stableFrameCount: scrollOptions.stableFrameCount ?? 2,
      maxFrameCount: scrollOptions.maxFrameCount ?? 8
    })
    updateSnapshot()
  }

  onMounted(async () => {
    await nextTick()
    setupObserver()
    updateSnapshot()
  })

  onBeforeUnmount(() => {
    teardownObserver()
  })

  watch(options.contentContainer, async () => {
    teardownObserver()
    await nextTick()
    setupObserver()
    updateSnapshot()
  })

  return {
    onScroll,
    resetPause,
    scrollToBottomAfterRender,
    teardown: teardownObserver
  }
}
