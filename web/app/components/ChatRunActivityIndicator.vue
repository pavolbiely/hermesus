<script setup lang="ts">
const props = defineProps<{
  label: string
}>()

const runningLabel = computed(() => {
  const match = props.label.match(/^Running\s+(.+)$/)
  const detail = match?.[1]
  if (!detail) return null

  return {
    status: 'Running',
    detail
  }
})
</script>

<template>
  <div class="flex min-w-0 items-center gap-2 overflow-visible text-muted" role="status" aria-live="polite">
    <span class="relative flex size-3 shrink-0 items-center justify-center overflow-visible" aria-hidden="true">
      <span class="absolute size-2.5 rounded-full bg-primary/30 animate-ping" />
      <span class="size-1.5 rounded-full bg-primary/80" />
    </span>
    <span v-if="runningLabel" class="inline-flex min-w-0 items-center gap-1 text-sm">
      <UChatShimmer :text="runningLabel.status" class="rainbow-chat-shimmer shrink-0" />
      <span class="min-w-0 truncate text-dimmed">{{ runningLabel.detail }}</span>
    </span>
    <UChatShimmer v-else :text="label" class="rainbow-chat-shimmer min-w-0 text-sm" />
  </div>
</template>
