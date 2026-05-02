<script setup lang="ts">
import type { WebChatFilePreview } from '~/types/web-chat'

const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{
  preview: WebChatFilePreview | null
  loading: boolean
  error: string | null
}>()

const isMarkdown = computed(() => props.preview?.language === 'markdown' || props.preview?.name.endsWith('.md'))
const isCodePreview = computed(() => Boolean(props.preview?.previewable && !isMarkdown.value))
const previewPath = computed(() => props.preview?.relativePath || props.preview?.path || props.preview?.requestedPath || 'File preview')
const meta = computed(() => {
  if (!props.preview) return null
  return `${props.preview.mediaType} · ${formatBytes(props.preview.size)}${props.preview.truncated ? ' · truncated' : ''}`
})
const markdownPreviewRoot = ref<HTMLElement | null>(null)
const highlightedCodeHtml = ref('')
let highlightRequestId = 0
let markdownHighlightObserver: MutationObserver | null = null
let markdownHighlightFrame: number | null = null

watch(
  () => ({
    content: props.preview?.content || '',
    isCodePreview: isCodePreview.value,
    language: props.preview?.language || 'text'
  }),
  async ({ content, isCodePreview, language }) => {
    const requestId = ++highlightRequestId
    highlightedCodeHtml.value = ''

    if (!isCodePreview) return

    const html = await highlightPreviewCode(content, language)
    if (requestId === highlightRequestId) highlightedCodeHtml.value = html
  },
  { immediate: true }
)

async function highlightPreviewCode(content: string, language: string) {
  try {
    return await renderShikiHtml(content, language)
  } catch (error) {
    console.error('Could not highlight file preview', error)
    return `<pre class="shiki" tabindex="0"><code>${escapeHtml(content)}</code></pre>`
  }
}

async function renderShikiHtml(content: string, language: string) {
  const { codeToHtml } = await import('shiki/bundle/web')
  return await codeToHtml(content, {
    lang: normalizeLanguage(language || 'text'),
    themes: {
      light: 'material-theme-lighter',
      dark: 'material-theme-palenight'
    },
    defaultColor: false
  })
}

function normalizeLanguage(language: string) {
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

function scheduleMarkdownHighlight() {
  if (!isMarkdown.value) return
  if (markdownHighlightFrame !== null) cancelAnimationFrame(markdownHighlightFrame)
  markdownHighlightFrame = requestAnimationFrame(() => {
    markdownHighlightFrame = null
    void highlightMarkdownCodeBlocks()
  })
}

async function highlightMarkdownCodeBlocks() {
  const root = markdownPreviewRoot.value
  if (!root || !isMarkdown.value) return

  const codeBlocks = [...root.querySelectorAll<HTMLElement>('pre > code[class*="language-"]')]
    .filter(code => !code.closest('pre')?.dataset.shikiHighlighted)

  await Promise.all(codeBlocks.map(highlightMarkdownCodeBlock))
}

async function highlightMarkdownCodeBlock(code: HTMLElement) {
  const pre = code.closest('pre')
  if (!pre) return

  const language = getCodeBlockLanguage(code)
  pre.dataset.shikiHighlighted = 'true'

  try {
    const html = await renderShikiHtml(code.textContent || '', language)
    pre.outerHTML = html
  } catch (error) {
    console.error(`Could not highlight markdown code block (${language})`, error)
    delete pre.dataset.shikiHighlighted
  }
}

function getCodeBlockLanguage(code: HTMLElement) {
  const languageClass = [...code.classList].find(className => className.startsWith('language-'))
  return languageClass?.replace(/^language-/, '') || 'text'
}

function observeMarkdownPreviewRoot(root: HTMLElement | null) {
  markdownHighlightObserver?.disconnect()
  markdownHighlightObserver = null

  if (!root) return
  markdownHighlightObserver = new MutationObserver(scheduleMarkdownHighlight)
  markdownHighlightObserver.observe(root, { childList: true, subtree: true })
  scheduleMarkdownHighlight()
}

watch(markdownPreviewRoot, observeMarkdownPreviewRoot)

onMounted(() => observeMarkdownPreviewRoot(markdownPreviewRoot.value))

onBeforeUnmount(() => {
  markdownHighlightObserver?.disconnect()
  if (markdownHighlightFrame !== null) cancelAnimationFrame(markdownHighlightFrame)
})

watch(() => props.preview?.content, () => nextTick(scheduleMarkdownHighlight))

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / 1024 ** exponent
  return `${value >= 10 || exponent === 0 ? Math.round(value) : value.toFixed(1)} ${units[exponent]}`
}
</script>

<template>
  <UModal v-model:open="open" :transition="false" :ui="{ content: 'sm:max-w-5xl', body: 'p-0' }">
    <template #content>
      <div class="relative flex h-[85vh] max-h-[calc(100dvh-2rem)] flex-col overflow-hidden rounded-lg bg-default shadow-xl ring ring-default">
        <div class="flex min-h-10 items-center gap-3 border-b border-default px-3 py-2">
          <div class="min-w-0 flex-1">
            <div class="truncate text-xs font-medium text-toned">
              {{ previewPath }}
            </div>
            <div v-if="meta" class="truncate text-[11px] leading-4 text-muted">
              {{ meta }}
            </div>
          </div>
          <UButton
            icon="i-lucide-x"
            color="neutral"
            variant="ghost"
            size="xs"
            class="shrink-0"
            aria-label="Close preview"
            @click="open = false"
          />
        </div>

        <div class="min-h-[60vh] flex-1 overflow-auto p-4">

          <div v-if="loading" class="flex min-h-[60vh] items-center justify-center gap-2 text-sm text-muted">
            <UIcon name="i-lucide-cpu" class="size-4 animate-spin" />
            <span>Loading preview…</span>
          </div>

          <div v-else-if="error" class="flex min-h-[60vh] flex-col items-center justify-center gap-2 text-center text-sm text-muted">
            <UIcon name="i-lucide-file-x" class="size-6" />
            <span>{{ error }}</span>
          </div>

          <div v-else-if="preview && !preview.previewable" class="flex min-h-40 flex-col items-center justify-center gap-2 text-center text-sm text-muted">
            <UIcon name="i-lucide-file-question" class="size-6" />
            <span>{{ preview.reason || 'File cannot be previewed.' }}</span>
          </div>

          <div v-else-if="preview && isMarkdown" ref="markdownPreviewRoot">
            <Comark
              :markdown="preview.content || ''"
              class="chat-file-preview-markdown *:first:mt-0 *:last:mb-0"
            />
          </div>

          <div
            v-else-if="preview && isCodePreview"
            class="chat-file-preview-code *:first:mt-0 *:last:mb-0"
            v-html="highlightedCodeHtml"
          />

          <pre
            v-else-if="preview"
            class="chat-file-preview-code overflow-x-auto rounded-md bg-muted/40 p-3 text-xs leading-5 whitespace-pre-wrap"
          ><code>{{ preview.content || '' }}</code></pre>
        </div>
      </div>
    </template>
  </UModal>
</template>
