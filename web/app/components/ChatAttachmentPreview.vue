<script setup lang="ts">
import type { WebChatAttachment } from '~/types/web-chat'

const props = defineProps<{
  attachment: WebChatAttachment
}>()

const api = useHermesApi()
const objectUrl = ref<string | null>(null)
const loadError = ref<string | null>(props.attachment.exists === false ? 'File no longer available' : null)
const loading = ref(false)
const isImage = computed(() => props.attachment.mediaType.startsWith('image/'))
const isMissing = computed(() => Boolean(loadError.value))
const fileSize = computed(() => formatBytes(props.attachment.size))

function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / 1024 ** exponent
  return `${value >= 10 || exponent === 0 ? Math.round(value) : value.toFixed(1)} ${units[exponent]}`
}

function clearObjectUrl() {
  if (objectUrl.value) URL.revokeObjectURL(objectUrl.value)
  objectUrl.value = null
}

async function loadContent() {
  if (import.meta.server || props.attachment.exists === false) return

  clearObjectUrl()
  loadError.value = null
  loading.value = true
  try {
    const blob = await api.fetchAttachmentContent(props.attachment)
    objectUrl.value = URL.createObjectURL(blob)
  } catch {
    loadError.value = 'File no longer available'
  } finally {
    loading.value = false
  }
}

function openFile() {
  if (!objectUrl.value) return
  window.open(objectUrl.value, '_blank', 'noopener,noreferrer')
}

watch(
  () => props.attachment.id,
  () => { void loadContent() },
  { immediate: true }
)

onBeforeUnmount(clearObjectUrl)
</script>

<template>
  <UCard v-if="isMissing" variant="subtle" class="w-56 opacity-75" :ui="{ body: 'p-3' }">
    <div class="flex items-center gap-2 text-sm text-muted">
      <UIcon name="i-lucide-file-x" class="size-4 shrink-0" />
      <span class="min-w-0 truncate">{{ attachment.name }}</span>
    </div>
    <p class="mt-1 text-xs text-muted">
      {{ loadError }}
    </p>
  </UCard>

  <div v-else-if="loading && isImage" class="w-64 overflow-hidden rounded-lg border border-default bg-muted">
    <div class="flex h-40 w-64 items-center justify-center">
      <UIcon name="i-lucide-loader-circle" class="size-5 animate-spin text-muted" />
    </div>
    <div class="flex w-64 items-center gap-2 px-2 py-1.5 text-xs text-muted">
      <UIcon name="i-lucide-image" class="size-3.5 shrink-0" />
      <span class="min-w-0 truncate">{{ attachment.name }}</span>
    </div>
  </div>

  <UCard v-else-if="loading" variant="subtle" class="w-56" :ui="{ body: 'p-3' }">
    <div class="flex items-center gap-2 text-sm text-muted">
      <UIcon name="i-lucide-loader-circle" class="size-4 shrink-0 animate-spin" />
      <span class="min-w-0 truncate">{{ attachment.name }}</span>
    </div>
    <p class="mt-1 text-xs text-muted">
      Loading preview…
    </p>
  </UCard>

  <UModal
    v-else-if="isImage && objectUrl"
    :title="attachment.name"
    :description="`${attachment.mediaType} · ${fileSize}`"
    :ui="{ content: 'sm:max-w-5xl', body: 'p-0' }"
  >
    <button type="button" class="group block w-64 overflow-hidden rounded-lg border border-default bg-muted text-left transition hover:border-accented">
      <img
        :src="objectUrl"
        :alt="attachment.name"
        width="256"
        height="160"
        class="h-40 w-64 object-contain transition group-hover:scale-[1.02]"
        loading="lazy"
        @error="loadError = 'File no longer available'"
      >
      <div class="flex w-64 items-center gap-2 px-2 py-1.5 text-xs text-muted">
        <UIcon name="i-lucide-image" class="size-3.5 shrink-0" />
        <span class="min-w-0 truncate">{{ attachment.name }}</span>
      </div>
    </button>

    <template #body>
      <div class="flex max-h-[80vh] items-center justify-center overflow-auto bg-elevated p-4">
        <img :src="objectUrl" :alt="attachment.name" class="max-h-[76vh] max-w-full object-contain" @error="loadError = 'File no longer available'">
      </div>
    </template>
  </UModal>

  <UCard v-else variant="subtle" class="w-64" :ui="{ body: 'p-3' }">
    <button type="button" class="flex w-full min-w-0 items-center gap-2 text-left text-sm text-highlighted hover:text-primary" @click="openFile">
      <UIcon name="i-lucide-file" class="size-4 shrink-0" />
      <span class="min-w-0 truncate">{{ attachment.name }}</span>
      <UIcon name="i-lucide-external-link" class="ml-auto size-3.5 shrink-0 text-muted" />
    </button>
    <p class="mt-1 truncate text-xs text-muted">
      {{ attachment.mediaType }} · {{ fileSize }}
    </p>
  </UCard>
</template>
