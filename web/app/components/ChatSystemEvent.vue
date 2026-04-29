<script setup lang="ts">
import type { WebChatPart } from '~/types/web-chat'
import { partText } from '~/utils/chatMessages'

const props = defineProps<{
  part: WebChatPart
}>()

const severity = computed(() => props.part.severity || 'info')
const icon = computed(() => {
  if (severity.value === 'error') return 'i-lucide-circle-alert'
  if (severity.value === 'warning') return 'i-lucide-triangle-alert'
  return 'i-lucide-info'
})
const title = computed(() => props.part.title || partText(props.part) || 'System event')
const description = computed(() => props.part.description || (props.part.title ? partText(props.part) : ''))
</script>

<template>
  <div class="my-2 flex justify-center px-2">
    <div
      class="inline-flex max-w-full items-start gap-2 rounded-full border px-3 py-1.5 text-xs shadow-sm"
      :class="{
        'border-error/30 bg-error/10 text-error': severity === 'error',
        'border-warning/30 bg-warning/10 text-warning': severity === 'warning',
        'border-default bg-muted/40 text-muted': severity !== 'error' && severity !== 'warning'
      }"
    >
      <UIcon :name="icon" class="mt-0.5 size-3.5 shrink-0" />
      <div class="min-w-0">
        <div class="truncate font-medium text-toned">{{ title }}</div>
        <div v-if="description" class="mt-0.5 whitespace-pre-wrap text-dimmed">{{ description }}</div>
      </div>
    </div>
  </div>
</template>
