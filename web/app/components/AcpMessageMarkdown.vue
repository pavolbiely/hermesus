<script setup lang="ts">
import type { AppFilePreview } from '~/types/chat'
import { isPreviewablePathCandidate, LOCAL_PATH_PATTERN, normalizePreviewPathCandidate } from '~/utils/filePreviewPaths'

const props = defineProps<{
  markdown: string
  workspace: string | null
  streaming?: boolean
}>()

const api = useAppWorkspacesApi()
const root = ref<HTMLElement | null>(null)
const previewOpen = ref(false)
const previewLoading = ref(false)
const previewError = ref<string | null>(null)
const previewRequestedPath = ref<string | null>(null)
const preview = ref<AppFilePreview | null>(null)
const existingPreviewPaths = new Set<string>()
const missingPreviewPaths = new Set<string>()
let observer: MutationObserver | null = null
let enhanceFrame: number | null = null
let highlightFrame: number | null = null
let resolveSequence = 0

type PreviewElementCandidate = {
  element: HTMLElement
  path: string
  href?: string | null
}

type PreviewCodeBlockCandidate = {
  container: HTMLElement
  path: string
}

type PreviewTextMatch = {
  raw: string
  path: string
  start: number
}

type PreviewTextCandidate = {
  node: Text
  matches: PreviewTextMatch[]
}

const enhancementSource = computed(() => [
  props.markdown,
  props.workspace,
  Boolean(props.streaming)
] as const)

function markPreviewTrigger(element: HTMLElement, path: string) {
  element.setAttribute('role', 'button')
  element.setAttribute('tabindex', '0')
  element.dataset.previewPath = path
  delete element.dataset.previewCandidatePath
  element.classList.add('chat-preview-path')
}

async function enhancePreviewPathNodes() {
  const element = root.value
  if (!element || props.streaming) return

  const elementCandidates = collectElementPreviewCandidates(element)
  const codeBlockCandidates = collectCodeBlockPreviewCandidates(element)
  const textCandidates = collectTextPreviewCandidates(element)
  const paths = new Set<string>()

  for (const candidate of elementCandidates) paths.add(candidate.path)
  for (const candidate of codeBlockCandidates) paths.add(candidate.path)
  for (const candidate of textCandidates) {
    for (const match of candidate.matches) paths.add(match.path)
  }

  await resolveExistingPreviewPaths([...paths])

  for (const candidate of elementCandidates) {
    if (!existingPreviewPaths.has(candidate.path)) continue
    if (candidate.href !== undefined) candidate.element.removeAttribute('href')
    markPreviewTrigger(candidate.element, candidate.path)
  }

  for (const candidate of codeBlockCandidates) {
    if (existingPreviewPaths.has(candidate.path)) markCodeBlockPreviewTrigger(candidate.container, candidate.path)
  }

  for (const candidate of textCandidates) {
    enhancePlainTextNode(candidate.node, candidate.matches.filter(match => existingPreviewPaths.has(match.path)))
  }
}

function collectElementPreviewCandidates(element: HTMLElement) {
  const candidates: PreviewElementCandidate[] = []

  for (const code of element.querySelectorAll<HTMLElement>('code')) {
    if (code.closest('pre') || code.dataset.previewPath) continue
    const path = normalizePreviewPathCandidate(code.textContent || '')
    if (isResolvablePreviewCandidate(path)) candidates.push({ element: code, path })
  }

  for (const link of element.querySelectorAll<HTMLAnchorElement>('a[href], a[data-preview-candidate-path]')) {
    if (link.dataset.previewPath) continue
    const href = link.dataset.previewCandidatePath || link.getAttribute('href') || ''
    const path = normalizePreviewPathCandidate(href)
    if (!isPreviewablePathCandidate(path)) continue
    link.dataset.previewCandidatePath = path
    link.removeAttribute('href')
    if (isResolvablePreviewCandidate(path)) candidates.push({ element: link, path, href })
  }

  return candidates
}

function collectCodeBlockPreviewCandidates(element: HTMLElement) {
  const candidates: PreviewCodeBlockCandidate[] = []

  for (const code of element.querySelectorAll<HTMLElement>('pre > code')) {
    const pre = code.closest('pre')
    const container = pre?.parentElement
    if (!pre || !container || container.dataset.previewCodePath) continue

    const path = normalizePreviewPathCandidate(code.textContent || '')
    if (isResolvablePreviewCandidate(path)) candidates.push({ container, path })
  }

  return candidates
}

function markCodeBlockPreviewTrigger(container: HTMLElement, path: string) {
  container.dataset.previewCodePath = path
  container.classList.add('chat-preview-code-block')

  const existing = container.querySelector<HTMLButtonElement>(':scope > [data-preview-code-action]')
  const button = existing ?? document.createElement('button')
  button.type = 'button'
  button.title = `Preview ${path}`
  button.setAttribute('aria-label', `Preview ${path}`)
  button.dataset.previewPath = path
  button.dataset.previewCodeAction = 'true'
  button.classList.add('chat-preview-code-action')
  button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m21 21-4.34-4.34"/><circle cx="11" cy="11" r="8"/></svg>'

  if (!existing) container.append(button)
}

function collectTextPreviewCandidates(element: HTMLElement) {
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement
      if (!parent || parent.closest('pre, code, a, button, input, textarea, [data-preview-path]')) {
        return NodeFilter.FILTER_REJECT
      }
      LOCAL_PATH_PATTERN.lastIndex = 0
      return LOCAL_PATH_PATTERN.test(node.textContent || '')
        ? NodeFilter.FILTER_ACCEPT
        : NodeFilter.FILTER_SKIP
    }
  })
  const candidates: PreviewTextCandidate[] = []

  while (walker.nextNode()) {
    const node = walker.currentNode as Text
    const matches = previewMatchesForText(node.textContent || '')
    if (matches.length) candidates.push({ node, matches })
  }

  return candidates
}

function previewMatchesForText(text: string) {
  const matches: PreviewTextMatch[] = []
  LOCAL_PATH_PATTERN.lastIndex = 0

  for (const match of text.matchAll(LOCAL_PATH_PATTERN)) {
    const raw = match[1]
    if (!raw || match.index === undefined) continue
    const start = match.index + match[0].lastIndexOf(raw)
    const path = normalizePreviewPathCandidate(raw)
    if (isResolvablePreviewCandidate(path)) matches.push({ raw, path, start })
  }

  return matches
}

function isResolvablePreviewCandidate(path: string) {
  return isPreviewablePathCandidate(path) && !missingPreviewPaths.has(path)
}

async function resolveExistingPreviewPaths(paths: string[]) {
  const unresolved = [...new Set(paths)].filter(path => !existingPreviewPaths.has(path) && !missingPreviewPaths.has(path))
  if (!unresolved.length) return

  const sequence = ++resolveSequence
  const workspace = props.workspace

  try {
    const { files } = await api.resolveFilePreviewPaths({ paths: unresolved, workspace })
    if (sequence !== resolveSequence || workspace !== props.workspace) return

    const found = new Set(files.map(reference => reference.requestedPath))
    for (const path of found) existingPreviewPaths.add(path)
    for (const path of unresolved) {
      if (!found.has(path)) missingPreviewPaths.add(path)
    }
  } catch {
    if (sequence !== resolveSequence || workspace !== props.workspace) return
    for (const path of unresolved) missingPreviewPaths.add(path)
  }
}

function enhancePlainTextNode(node: Text, matches: PreviewTextMatch[]) {
  if (!matches.length || !node.isConnected) return
  const text = node.textContent || ''
  const fragment = document.createDocumentFragment()
  let cursor = 0

  for (const match of matches) {
    if (match.start < cursor) continue
    if (match.start > cursor) fragment.append(document.createTextNode(text.slice(cursor, match.start)))
    const button = document.createElement('button')
    button.type = 'button'
    button.textContent = match.raw
    markPreviewTrigger(button, match.path)
    fragment.append(button)
    cursor = match.start + match.raw.length
  }

  if (cursor < text.length) fragment.append(document.createTextNode(text.slice(cursor)))
  node.parentNode?.replaceChild(fragment, node)
}

function previewPathFromEvent(event: Event) {
  const target = event.target instanceof Element ? event.target.closest<HTMLElement>('[data-preview-path]') : null
  return target?.dataset.previewPath || null
}

async function openFilePreview(path: string) {
  previewRequestedPath.value = path
  previewOpen.value = true
  previewLoading.value = true
  previewError.value = null
  preview.value = null

  try {
    preview.value = await api.fetchFilePreview({ path, workspace: props.workspace })
  } catch (error) {
    previewError.value = error instanceof Error ? error.message : 'Could not load preview'
  } finally {
    previewLoading.value = false
  }
}

function cancelEnhancement() {
  if (enhanceFrame === null || typeof window === 'undefined') return
  window.cancelAnimationFrame(enhanceFrame)
  enhanceFrame = null
}

function scheduleEnhancement() {
  if (typeof window === 'undefined') return
  if (props.streaming) {
    cancelEnhancement()
    return
  }
  cancelEnhancement()
  enhanceFrame = window.requestAnimationFrame(() => {
    enhanceFrame = null
    void enhancePreviewPathNodes()
  })
}

function onPreviewClick(event: MouseEvent) {
  const path = previewPathFromEvent(event)
  if (!path) return
  event.preventDefault()
  void openFilePreview(path)
}

function onPreviewKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' && event.key !== ' ') return
  const path = previewPathFromEvent(event)
  if (!path) return
  event.preventDefault()
  void openFilePreview(path)
}

function scheduleMarkdownHighlight() {
  if (typeof window === 'undefined') return
  if (highlightFrame !== null) {
    window.cancelAnimationFrame(highlightFrame)
    highlightFrame = null
  }
  if (props.streaming) return
  highlightFrame = window.requestAnimationFrame(() => {
    highlightFrame = null
    void highlightMarkdownCodeBlocks()
  })
}

async function highlightMarkdownCodeBlocks() {
  const element = root.value
  if (!element || props.streaming) return

  const codeBlocks = [...element.querySelectorAll<HTMLElement>('pre > code[class*="language-"]')]
    .filter(code => !code.closest('pre')?.dataset.shikiHighlighted)

  await Promise.all(codeBlocks.map(highlightMarkdownCodeBlock))
}

async function highlightMarkdownCodeBlock(code: HTMLElement) {
  const pre = code.closest('pre')
  if (!pre) return

  const language = codeBlockLanguage(code)
  pre.dataset.shikiHighlighted = 'true'

  try {
    const { codeToHtml } = await import('shiki/bundle/web')
    pre.outerHTML = await codeToHtml(code.textContent || '', {
      lang: normalizeHighlightLanguage(language),
      themes: {
        light: 'material-theme-lighter',
        dark: 'material-theme-palenight'
      },
      defaultColor: false
    })
  } catch (error) {
    console.error(`Could not highlight chat code block (${language})`, error)
    delete pre.dataset.shikiHighlighted
  }
}

function codeBlockLanguage(code: HTMLElement) {
  const languageClass = [...code.classList].find(className => className.startsWith('language-'))
  return languageClass?.replace(/^language-/, '') || 'text'
}

function normalizeHighlightLanguage(language: string) {
  const value = language.trim().toLowerCase()
  const aliases: Record<string, string> = {
    cs: 'csharp',
    js: 'javascript',
    md: 'markdown',
    py: 'python',
    rs: 'rust',
    sh: 'bash',
    ts: 'typescript',
    yml: 'yaml'
  }
  return aliases[value] || value || 'text'
}

function resetPreviewPathResolution() {
  resolveSequence += 1
  existingPreviewPaths.clear()
  missingPreviewPaths.clear()
}

watch(
  enhancementSource,
  async () => {
    resetPreviewPathResolution()
    await nextTick()
    scheduleMarkdownHighlight()
    scheduleEnhancement()
  },
  { immediate: true, flush: 'post' }
)

onMounted(async () => {
  await nextTick()
  const element = root.value
  if (!element || typeof MutationObserver === 'undefined') {
    scheduleEnhancement()
    return
  }

  observer = new MutationObserver(() => {
    scheduleMarkdownHighlight()
    scheduleEnhancement()
  })
  observer.observe(element, { childList: true, subtree: true })
  scheduleMarkdownHighlight()
  scheduleEnhancement()
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
  cancelEnhancement()
  if (highlightFrame !== null) window.cancelAnimationFrame(highlightFrame)
})
</script>

<template>
  <div
    ref="root"
    class="chat-message-markdown prose prose-sm dark:prose-invert max-w-none"
    @click="onPreviewClick"
    @keydown="onPreviewKeydown"
  >
    <Comark :markdown="markdown" />
  </div>

  <ChatFilePreviewModal
    v-model:open="previewOpen"
    :preview="preview"
    :requested-path="previewRequestedPath"
    :loading="previewLoading"
    :error="previewError"
  />
</template>
