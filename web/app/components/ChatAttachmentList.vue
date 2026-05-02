<script setup lang="ts">
import type { WebChatAttachment } from '~/types/web-chat'

type ChatAttachmentListProps = {
  attachments?: WebChatAttachment[]
  disabled?: boolean
}

const props = withDefaults(defineProps<ChatAttachmentListProps>(), {
  attachments: () => [],
  disabled: false
})

const emit = defineEmits<{
  remove: [id: string]
}>()

const api = useHermesApi()
const previewUrls = reactive(new Map<string, string>())
const previewErrors = reactive(new Map<string, string>())
const loadingPreviewIds = reactive(new Set<string>())
let disposed = false

function isImageAttachment(attachment: WebChatAttachment) {
  return attachment.mediaType.startsWith('image/')
}

function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / 1024 ** exponent
  return `${value >= 10 || exponent === 0 ? Math.round(value) : value.toFixed(1)} ${units[exponent]}`
}

function clearPreviewUrl(id: string) {
  const url = previewUrls.get(id)
  if (url) URL.revokeObjectURL(url)
  previewUrls.delete(id)
}

async function loadImagePreview(attachment: WebChatAttachment) {
  if (import.meta.server || !isImageAttachment(attachment) || attachment.exists === false) return
  if (previewUrls.has(attachment.id) || loadingPreviewIds.has(attachment.id)) return

  previewErrors.delete(attachment.id)
  loadingPreviewIds.add(attachment.id)

  try {
    const blob = await api.fetchAttachmentContent(attachment)
    if (disposed || !props.attachments.some(item => item.id === attachment.id)) return
    clearPreviewUrl(attachment.id)
    previewUrls.set(attachment.id, URL.createObjectURL(blob))
  } catch {
    previewErrors.set(attachment.id, 'Preview unavailable')
  } finally {
    loadingPreviewIds.delete(attachment.id)
  }
}

function removeAttachment(id: string) {
  clearPreviewUrl(id)
  previewErrors.delete(id)
  loadingPreviewIds.delete(id)
  emit('remove', id)
}

watch(
  () => props.attachments.map(attachment => attachment.id),
  (ids) => {
    const activeIds = new Set(ids)
    for (const id of previewUrls.keys()) {
      if (!activeIds.has(id)) clearPreviewUrl(id)
    }
    for (const id of previewErrors.keys()) {
      if (!activeIds.has(id)) previewErrors.delete(id)
    }
    for (const id of loadingPreviewIds.keys()) {
      if (!activeIds.has(id)) loadingPreviewIds.delete(id)
    }
  }
)

onBeforeUnmount(() => {
  disposed = true
  for (const id of previewUrls.keys()) clearPreviewUrl(id)
})
</script>

<template>
  <div v-if="attachments.length" class="flex min-w-0 flex-wrap gap-1.5 px-1">
    <template v-for="attachment in attachments" :key="attachment.id">
      <UPopover
        v-if="isImageAttachment(attachment)"
        mode="hover"
        :open-delay="500"
        :content="{ side: 'top', align: 'center', sideOffset: 8 }"
        :ui="{ content: 'w-52 p-0 overflow-hidden' }"
      >
        <UBadge
          color="neutral"
          variant="soft"
          class="max-w-48 cursor-default gap-1"
          @mouseenter="loadImagePreview(attachment)"
        >
          <UIcon name="i-lucide-image" class="size-3.5 shrink-0" />
          <span class="truncate">{{ attachment.name }}</span>
          <UButton
            icon="i-lucide-x"
            color="neutral"
            variant="ghost"
            size="xs"
            class="size-4 p-0"
            :ui="{ leadingIcon: 'size-3' }"
            :disabled="disabled"
            aria-label="Remove attachment"
            @click="removeAttachment(attachment.id)"
          />
        </UBadge>

        <template #content>
          <div class="w-52 bg-elevated text-xs">
            <div class="flex h-32 w-52 items-center justify-center bg-muted/60">
              <img
                v-if="previewUrls.get(attachment.id)"
                :src="previewUrls.get(attachment.id)"
                :alt="attachment.name"
                class="max-h-32 max-w-52 object-contain"
                loading="lazy"
                @error="previewErrors.set(attachment.id, 'Preview unavailable')"
              >
              <UIcon
                v-else-if="loadingPreviewIds.has(attachment.id)"
                name="i-lucide-cpu"
                class="size-4 animate-spin text-muted"
              />
              <div v-else class="flex flex-col items-center gap-1 px-3 text-center text-muted">
                <UIcon name="i-lucide-image-off" class="size-4" />
                <span>{{ attachment.exists === false ? 'File no longer available' : previewErrors.get(attachment.id) || 'Preview unavailable' }}</span>
              </div>
            </div>
            <div class="flex items-center gap-1.5 border-t border-default px-2 py-1.5 text-muted">
              <UIcon name="i-lucide-image" class="size-3.5 shrink-0" />
              <span class="min-w-0 truncate">{{ attachment.name }}</span>
              <span class="shrink-0 text-muted/80">{{ formatBytes(attachment.size) }}</span>
            </div>
          </div>
        </template>
      </UPopover>

      <UBadge
        v-else
        color="neutral"
        variant="soft"
        class="max-w-48 cursor-default gap-1"
      >
        <UIcon name="i-lucide-file" class="size-3.5 shrink-0" />
        <span class="truncate">{{ attachment.name }}</span>
        <UButton
          icon="i-lucide-x"
          color="neutral"
          variant="ghost"
          size="xs"
          class="size-4 p-0"
          :ui="{ leadingIcon: 'size-3' }"
          :disabled="disabled"
          aria-label="Remove attachment"
          @click="removeAttachment(attachment.id)"
        />
      </UBadge>
    </template>
  </div>
</template>
