type BottomScrollOptions = {
  waitForDomUpdate?: () => Promise<void> | void
  waitForFrame?: () => Promise<void> | void
  frameCount?: number
  stableFrameCount?: number
  maxFrameCount?: number
}

type RectLike = {
  top: number
  bottom: number
  height?: number
}

type RectElement = {
  getBoundingClientRect?: () => RectLike
}

function scrollableElementsFor(element?: HTMLElement | null) {
  const elements: Element[] = []
  let current: HTMLElement | null = element ?? null

  while (current) {
    if (current.scrollHeight > current.clientHeight) elements.push(current)
    current = current.parentElement
  }

  const scrollingElement = document.scrollingElement
  if (scrollingElement && scrollingElement.scrollHeight > scrollingElement.clientHeight) elements.push(scrollingElement)

  return elements
}

function scrollElementToBottom(element: Element) {
  element.scrollTop = element.scrollHeight
}

function scrollDistanceFromBottom(element: Element) {
  return Math.max(0, element.scrollHeight - element.clientHeight - element.scrollTop)
}

function scrollSnapshot(elements: Element[]) {
  return elements.map(element => `${element.scrollHeight}:${element.clientHeight}:${Math.round(element.scrollTop)}`).join('|')
}

export function scrollElementTreeToBottom(element?: HTMLElement | null) {
  const scrolled = new Set<Element>()
  const elements = scrollableElementsFor(element)

  for (const item of elements) {
    scrollElementToBottom(item)
    scrolled.add(item)
  }

  return scrolled.size
}

export async function scrollElementTreeToBottomAfterRender(
  element?: HTMLElement | null,
  options: BottomScrollOptions = {}
) {
  await options.waitForDomUpdate?.()

  const initialFrameCount = Math.max(1, options.frameCount ?? 1)
  for (let index = 0; index < initialFrameCount; index += 1) {
    await options.waitForFrame?.()
  }

  const stableFrameCount = Math.max(1, options.stableFrameCount ?? 2)
  const maxFrameCount = Math.max(stableFrameCount, options.maxFrameCount ?? 12)
  let stableFrames = 0
  let previousSnapshot = ''
  let scrolledCount = 0

  for (let index = 0; index < maxFrameCount; index += 1) {
    const elements = scrollableElementsFor(element)
    for (const item of elements) scrollElementToBottom(item)
    scrolledCount = new Set(elements).size

    const nextSnapshot = scrollSnapshot(elements)
    const isAtBottom = elements.every(item => scrollDistanceFromBottom(item) <= 1)
    stableFrames = nextSnapshot === previousSnapshot && isAtBottom ? stableFrames + 1 : 0
    previousSnapshot = nextSnapshot

    if (stableFrames >= stableFrameCount) break
    await options.waitForFrame?.()
  }

  return scrolledCount
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
