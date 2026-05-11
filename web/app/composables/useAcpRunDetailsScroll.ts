import { nextTick, onBeforeUnmount } from 'vue'
import type { ComponentPublicInstance, Ref } from 'vue'

type RunDetailsScrollOptions = {
  scrollContainer: Ref<HTMLElement | null>
}

export function useAcpRunDetailsScroll(options: RunDetailsScrollOptions) {
  const elements = new Map<string, HTMLElement>()
  const cleanupCallbacks = new Map<string, () => void>()

  function setRunDetailsElement(messageId: string, element: Element | ComponentPublicInstance | null) {
    const root = resolveHtmlRoot(element)
    if (root) {
      elements.set(messageId, root)
    } else {
      elements.delete(messageId)
    }
  }

  function onRunDetailsOpen(open: boolean, messageId: string) {
    cleanupCallbacks.get(messageId)?.()
    cleanupCallbacks.delete(messageId)
    if (!open) return
    void scrollRunDetailsExpansionIntoView(messageId)
  }

  async function scrollRunDetailsExpansionIntoView(messageId: string) {
    await nextTick()

    const container = options.scrollContainer.value
    const element = elements.get(messageId)
    if (!container || !element) return

    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const scrollIfNeeded = () => {
      const containerRect = container.getBoundingClientRect()
      const elementRect = element.getBoundingClientRect()
      const bottomGap = 12
      const overflow = elementRect.bottom - containerRect.bottom + bottomGap
      if (overflow <= 0) return

      container.scrollTo({
        top: container.scrollTop + overflow,
        behavior: prefersReducedMotion ? 'auto' : 'smooth'
      })
    }

    let frame = requestAnimationFrame(scrollIfNeeded)
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(scrollIfNeeded)
    })
    observer.observe(element)

    const timers = [120, 260, 420].map(delay => window.setTimeout(scrollIfNeeded, delay))
    const cleanup = () => {
      observer.disconnect()
      cancelAnimationFrame(frame)
      timers.forEach(timer => window.clearTimeout(timer))
    }
    cleanupCallbacks.set(messageId, cleanup)
    window.setTimeout(() => {
      cleanup()
      if (cleanupCallbacks.get(messageId) === cleanup) {
        cleanupCallbacks.delete(messageId)
      }
    }, 500)
  }

  function cleanupRunDetailsScroll() {
    cleanupCallbacks.forEach(cleanup => cleanup())
    cleanupCallbacks.clear()
    elements.clear()
  }

  onBeforeUnmount(cleanupRunDetailsScroll)

  return {
    setRunDetailsElement,
    onRunDetailsOpen,
    cleanupRunDetailsScroll
  }
}

function resolveHtmlRoot(element: Element | ComponentPublicInstance | null) {
  if (element instanceof HTMLElement) return element
  if (isComponentWithHtmlRoot(element)) return element.$el
  return null
}

function isComponentWithHtmlRoot(value: Element | ComponentPublicInstance | null): value is ComponentPublicInstance & { $el: HTMLElement } {
  return Boolean(value && typeof value === 'object' && '$el' in value && value.$el instanceof HTMLElement)
}
