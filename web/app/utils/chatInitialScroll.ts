type InitialScrollState = {
  currentSessionId: string
  loadedSessionId?: string | null
  settledSessionId?: string | null
  isLoading: boolean
  hasSession: boolean
}

export function shouldHideChatUntilInitialScroll(state: InitialScrollState) {
  if (state.isLoading || !state.hasSession) return false
  if (state.loadedSessionId !== state.currentSessionId) return false

  return state.settledSessionId !== state.currentSessionId
}

type BottomScrollOptions = {
  waitForDomUpdate?: () => Promise<void> | void
  waitForFrame?: () => Promise<void> | void
  frameCount?: number
}

type RectLike = {
  top: number
  bottom: number
  height?: number
}

type RectElement = {
  getBoundingClientRect?: () => RectLike
}

export function scrollElementTreeToBottom(element?: HTMLElement | null) {
  const scrolled = new Set<Element>()
  let current: HTMLElement | null = element ?? null

  while (current) {
    if (current.scrollHeight > current.clientHeight) {
      current.scrollTop = current.scrollHeight
      scrolled.add(current)
    }
    current = current.parentElement
  }

  const scrollingElement = document.scrollingElement
  if (scrollingElement && scrollingElement.scrollHeight > scrollingElement.clientHeight) {
    scrollingElement.scrollTop = scrollingElement.scrollHeight
    scrolled.add(scrollingElement)
  }

  return scrolled.size
}

export async function scrollElementTreeToBottomAfterRender(
  element?: HTMLElement | null,
  options: BottomScrollOptions = {}
) {
  await options.waitForDomUpdate?.()
  const frameCount = Math.max(1, options.frameCount ?? 1)
  for (let index = 0; index < frameCount; index += 1) {
    await options.waitForFrame?.()
  }
  return scrollElementTreeToBottom(element)
}

export function nearestScrollableAncestor(element?: HTMLElement | null) {
  let current: HTMLElement | null = element ?? null

  while (current) {
    if (current.scrollHeight > current.clientHeight) return current
    current = current.parentElement
  }

  return document.scrollingElement ?? null
}

export function isElementVisibleInRoot(element?: RectElement | null, root?: RectElement | null) {
  if (!element?.getBoundingClientRect) return false

  const rect = element.getBoundingClientRect()
  const rootRect = root?.getBoundingClientRect?.() ?? {
    top: 0,
    bottom: window.innerHeight || document.documentElement.clientHeight,
    height: window.innerHeight || document.documentElement.clientHeight
  }
  const visibleHeight = Math.min(rect.bottom, rootRect.bottom) - Math.max(rect.top, rootRect.top)
  const minimumVisibleHeight = Math.min(Math.max(1, rect.height ?? rect.bottom - rect.top), 24)

  return visibleHeight >= minimumVisibleHeight
}
