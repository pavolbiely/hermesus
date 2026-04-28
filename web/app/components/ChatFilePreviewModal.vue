<script setup lang="ts">
import highlight from '@comark/nuxt/plugins/highlight'
import type { WebChatFilePreview } from '~/types/web-chat'

const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{
  preview: WebChatFilePreview | null
  loading: boolean
  error: string | null
}>()

const isMarkdown = computed(() => props.preview?.language === 'markdown' || props.preview?.name.endsWith('.md'))
const previewPath = computed(() => props.preview?.relativePath || props.preview?.path || props.preview?.requestedPath || 'File preview')
const meta = computed(() => {
  if (!props.preview) return null
  return `${props.preview.mediaType} · ${formatBytes(props.preview.size)}${props.preview.truncated ? ' · truncated' : ''}`
})
const codeLines = computed(() => splitPreviewLines(props.preview?.content || ''))

function splitPreviewLines(content: string) {
  if (!content) return ['']
  const lines = content.split('\n')
  if (lines.length > 1 && lines[lines.length - 1] === '') lines.pop()
  return lines
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
  <UModal v-model:open="open" :ui="{ content: 'sm:max-w-5xl', body: 'p-0' }">
    <template #content>
      <div class="relative flex max-h-[85vh] flex-col overflow-hidden rounded-lg bg-default shadow-xl ring ring-default">
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

        <div class="min-h-0 flex-1 overflow-auto p-4">

          <div v-if="loading" class="flex min-h-40 items-center justify-center gap-2 text-sm text-muted">
            <UIcon name="i-lucide-loader-circle" class="size-4 animate-spin" />
            <span>Loading preview…</span>
          </div>

          <div v-else-if="error" class="flex min-h-40 flex-col items-center justify-center gap-2 text-center text-sm text-muted">
            <UIcon name="i-lucide-file-x" class="size-6" />
            <span>{{ error }}</span>
          </div>

          <div v-else-if="preview && !preview.previewable" class="flex min-h-40 flex-col items-center justify-center gap-2 text-center text-sm text-muted">
            <UIcon name="i-lucide-file-question" class="size-6" />
            <span>{{ preview.reason || 'File cannot be previewed.' }}</span>
          </div>

          <Comark
            v-else-if="preview && isMarkdown"
            :markdown="preview.content || ''"
            :plugins="[highlight()]"
            class="chat-file-preview-markdown *:first:mt-0 *:last:mb-0"
          />

          <pre
            v-else-if="preview"
            class="chat-file-preview-code overflow-x-auto rounded-md bg-muted/40 py-3 text-xs leading-5"
          ><code><span
            v-for="(line, index) in codeLines"
            :key="index"
            class="chat-file-preview-line"
          ><span class="chat-file-preview-line-number">{{ index + 1 }}</span><span class="chat-file-preview-line-content">{{ line || ' ' }}</span></span></code></pre>
        </div>
      </div>
    </template>
  </UModal>
</template>
