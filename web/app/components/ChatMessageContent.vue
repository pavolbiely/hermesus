<script setup lang="ts">
import type { WebChatFilePreview, WebChatMessage, WebChatPart } from '~/types/web-chat'
import { isPreviewablePathCandidate, LOCAL_PATH_PATTERN, normalizePreviewPathCandidate } from '~/utils/filePreviewPaths'
import { groupMessageParts, messagePartKey, partText } from '~/utils/chatMessages'
import { createMarkdownHighlightPlugin } from '~/utils/markdownHighlight'

const editingText = defineModel<string>('editingText', { required: true })
const api = useHermesApi()
const filePreviewCache = useFilePreviewCache()
const messageContentRoot = ref<HTMLElement | null>(null)
const previewOpen = ref(false)
const previewLoading = ref(false)
const previewError = ref<string | null>(null)
const preview = ref<WebChatFilePreview | null>(null)
let previewPathObserver: MutationObserver | null = null
let enhancePreviewFrame: number | null = null
let previewResolveSequence = 0
const existingPreviewPaths = new Set<string>()
const missingPreviewPaths = new Set<string>()

type PreviewElementCandidate = {
  element: HTMLElement
  path: string
  href?: string | null
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

const markdownPlugins = [createMarkdownHighlightPlugin()]

const props = defineProps<{
  message: WebChatMessage
  copiedMessageId: string | null
  editingMessageId: string | null
  savingEditedMessageId: string | null
  isRunning: boolean
  isActiveRunMessage: boolean
  workspace: string | null
  setEditingMessageContainer: (el: unknown) => void
  latestChangePartKey: string | null
}>()

const shouldPausePreviewEnhancement = computed(() => props.isRunning && props.isActiveRunMessage && props.message.role === 'assistant')
const { generatingMessageId, speakingMessageId } = useMessageReadAloud()
const isMessageReadAloudActive = computed(() => props.message.role === 'assistant' && (
  speakingMessageId.value === props.message.id || generatingMessageId.value === props.message.id
))
const previewEnhancementSource = computed(() => [
  props.message.id,
  props.workspace,
  shouldPausePreviewEnhancement.value,
  shouldPausePreviewEnhancement.value ? '' : props.message.parts.map(part => partText(part)).join('\n')
] as const)

function isLatestChangePart(message: WebChatMessage, part: WebChatPart) {
  return messagePartKey(message, part) === props.latestChangePartKey
}

function isPrimaryContentPart(part: WebChatPart) {
  if (part.type === 'text') return Boolean(partText(part).trim())
  return part.type === 'media' || part.type === 'interactive_prompt' || part.type === 'changes'
}

const showMessageFooter = computed(() => {
  if (props.message.role === 'system') return false
  if (props.isActiveRunMessage && !isMessageReadAloudActive.value) return false
  if (props.message.role === 'assistant') return props.message.parts.some(isPrimaryContentPart)
  return true
})

const emit = defineEmits<{
  copy: [message: WebChatMessage]
  regenerate: [message: WebChatMessage]
  edit: [message: WebChatMessage]
  cancelEdit: []
  saveEdit: [message: WebChatMessage]
  retryFailed: [message: WebChatMessage]
  editFailed: [message: WebChatMessage]
}>()

function markPreviewTrigger(element: HTMLElement, path: string) {
  element.setAttribute('role', 'button')
  element.setAttribute('tabindex', '0')
  element.dataset.previewPath = path
  delete element.dataset.previewCandidatePath
  element.classList.add('chat-preview-path')
}

async function enhancePreviewPathNodes() {
  const root = messageContentRoot.value
  if (!root || props.message.role !== 'assistant') return

  const elementCandidates = collectElementPreviewCandidates(root)
  const textCandidates = collectTextPreviewCandidates(root)
  const paths = new Set<string>()

  for (const candidate of elementCandidates) paths.add(candidate.path)
  for (const candidate of textCandidates) {
    for (const match of candidate.matches) paths.add(match.path)
  }

  await resolveExistingPreviewPaths([...paths])

  for (const candidate of elementCandidates) {
    if (!existingPreviewPaths.has(candidate.path)) continue
    if (candidate.href !== undefined) (candidate.element as HTMLAnchorElement).removeAttribute('href')
    markPreviewTrigger(candidate.element, candidate.path)
  }

  for (const candidate of textCandidates) {
    enhancePlainTextNode(candidate.node, candidate.matches.filter(match => existingPreviewPaths.has(match.path)))
  }
}

function collectElementPreviewCandidates(root: HTMLElement) {
  const candidates: PreviewElementCandidate[] = []

  for (const code of root.querySelectorAll<HTMLElement>('code')) {
    if (code.closest('pre') || code.dataset.previewPath) continue
    const path = normalizePreviewPathCandidate(code.textContent || '')
    if (isResolvablePreviewCandidate(path)) candidates.push({ element: code, path })
  }

  for (const link of root.querySelectorAll<HTMLAnchorElement>('a[href], a[data-preview-candidate-path]')) {
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

function collectTextPreviewCandidates(root: HTMLElement) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
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

  const sequence = ++previewResolveSequence
  const workspace = props.workspace

  try {
    const references = await api.resolveFilePreviewPaths({ paths: unresolved, workspace })
    if (sequence !== previewResolveSequence || workspace !== props.workspace) return

    const found = new Set(references.map(reference => reference.requestedPath))
    for (const path of found) existingPreviewPaths.add(path)
    for (const path of unresolved) {
      if (!found.has(path)) missingPreviewPaths.add(path)
    }
  } catch {
    if (sequence !== previewResolveSequence || workspace !== props.workspace) return
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

function waitForPreviewModalPaint() {
  if (typeof window === 'undefined') return nextTick()
  return new Promise<void>((resolve) => {
    void nextTick(() => {
      window.requestAnimationFrame(() => resolve())
    })
  })
}

async function openFilePreview(path: string) {
  previewOpen.value = true
  previewLoading.value = true
  previewError.value = null
  preview.value = null

  await waitForPreviewModalPaint()

  try {
    preview.value = await filePreviewCache.fetchFilePreview({ path, workspace: props.workspace })
  } catch (err) {
    previewError.value = err instanceof Error ? err.message : 'Could not load preview'
  } finally {
    previewLoading.value = false
  }
}

function cancelEnhancePreviewPathNodes() {
  if (enhancePreviewFrame === null || typeof window === 'undefined') return
  window.cancelAnimationFrame(enhancePreviewFrame)
  enhancePreviewFrame = null
}

function scheduleEnhancePreviewPathNodes() {
  if (typeof window === 'undefined') return
  if (shouldPausePreviewEnhancement.value) {
    cancelEnhancePreviewPathNodes()
    return
  }
  cancelEnhancePreviewPathNodes()
  enhancePreviewFrame = window.requestAnimationFrame(() => {
    enhancePreviewFrame = null
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

function resetPreviewPathResolution() {
  previewResolveSequence += 1
  existingPreviewPaths.clear()
  missingPreviewPaths.clear()
}

watch(
  previewEnhancementSource,
  async () => {
    if (shouldPausePreviewEnhancement.value) {
      cancelEnhancePreviewPathNodes()
      return
    }

    resetPreviewPathResolution()
    await nextTick()
    scheduleEnhancePreviewPathNodes()
  },
  { immediate: true, flush: 'post' }
)

onMounted(async () => {
  await nextTick()
  const root = messageContentRoot.value
  if (!root || typeof MutationObserver === 'undefined') {
    scheduleEnhancePreviewPathNodes()
    return
  }

  previewPathObserver = new MutationObserver(() => scheduleEnhancePreviewPathNodes())
  previewPathObserver.observe(root, { childList: true, subtree: true })
  scheduleEnhancePreviewPathNodes()
})

onBeforeUnmount(() => {
  previewPathObserver?.disconnect()
  previewPathObserver = null
  cancelEnhancePreviewPathNodes()
})
</script>

<template>
  <div ref="messageContentRoot" class="min-w-0 max-w-full" @click="onPreviewClick" @keydown="onPreviewKeydown">
    <template v-for="(group, index) in groupMessageParts(message.parts)" :key="`${message.id}-${group.type}-${index}`">
    <RunDetailsGroup
      v-if="group.type === 'process'"
      :parts="group.parts"
      :expanded-default="isActiveRunMessage"
    />

    <template v-else>
      <div v-if="group.part.type === 'media' && group.part.attachments?.length" class="mb-2 flex flex-wrap gap-2">
        <ChatAttachmentPreview
          v-for="attachment in group.part.attachments"
          :key="attachment.id"
          :attachment="attachment"
        />
      </div>

      <ChatChangeSummary
        v-else-if="group.part.type === 'changes' && group.part.changes"
        :changes="group.part.changes"
        :initially-open="isLatestChangePart(message, group.part)"
      />

      <ChatSystemEvent
        v-else-if="group.part.type === 'event'"
        :part="group.part"
      />

      <InteractivePromptCard
        v-else-if="group.part.type === 'interactive_prompt' && group.part.prompt"
        :prompt="group.part.prompt"
      />

      <div
        v-else-if="group.part.type === 'steer'"
        class="rounded-lg border border-dashed border-default bg-muted/30 px-3 py-2 text-sm text-muted"
      >
        <div class="mb-1 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-dimmed">
          <UIcon name="i-lucide-route" class="size-3.5" />
          <span>Steer</span>
        </div>
        <p class="whitespace-pre-wrap text-toned">
          {{ partText(group.part) }}
        </p>
      </div>

      <template v-else-if="group.part.type === 'text'">
        <Comark
          v-if="message.role === 'assistant'"
          :markdown="partText(group.part)"
          :plugins="markdownPlugins"
          class="chat-message-markdown *:first:mt-0 *:last:mb-0"
        />
        <div v-else-if="editingMessageId === message.id" :ref="setEditingMessageContainer" class="w-full">
          <UChatPrompt
            v-model="editingText"
            :disabled="savingEditedMessageId === message.id"
            :rows="3"
            :autofocus="true"
            :autoresize="true"
            :ui="{ footer: 'justify-end' }"
            class="w-full min-w-72"
            @submit="emit('saveEdit', message)"
            @keydown.esc.prevent="emit('cancelEdit')"
          >
            <template #footer>
              <div class="flex w-full justify-end gap-2">
                <UButton
                  size="xs"
                  color="neutral"
                  variant="ghost"
                  label="Cancel"
                  :disabled="savingEditedMessageId === message.id"
                  @click="emit('cancelEdit')"
                />
                <UButton
                  size="xs"
                  color="primary"
                  variant="soft"
                  label="Save"
                  :loading="savingEditedMessageId === message.id"
                  :disabled="!editingText.trim()"
                  @click="emit('saveEdit', message)"
                />
              </div>
            </template>
          </UChatPrompt>
        </div>
        <p v-else class="chat-message-plain whitespace-pre-wrap">
          {{ partText(group.part) }}
        </p>
      </template>
    </template>
  </template>

  <div
    v-if="message.role === 'user' && message.localStatus === 'failed'"
    class="mt-2 flex flex-wrap items-center justify-end gap-2 text-xs text-error"
  >
    <span>{{ message.localError || 'Not sent' }}</span>
    <UButton size="xs" color="error" variant="soft" label="Retry" @click="emit('retryFailed', message)" />
    <UButton size="xs" color="neutral" variant="ghost" label="Edit" @click="emit('editFailed', message)" />
  </div>

  <ChatMessageFooter
    v-if="showMessageFooter"
    :message="message"
    :copied-message-id="copiedMessageId"
    :saving-edited-message-id="savingEditedMessageId"
    :is-running="isRunning"
    @copy="emit('copy', $event)"
    @regenerate="emit('regenerate', $event)"
    @edit="emit('edit', $event)"
  />
  </div>

  <ChatFilePreviewModal
    v-model:open="previewOpen"
    :preview="preview"
    :loading="previewLoading"
    :error="previewError"
  />
</template>
