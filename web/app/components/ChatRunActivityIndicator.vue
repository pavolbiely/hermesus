<script setup lang="ts">
defineProps<{
  label: string
}>()
</script>

<template>
  <div class="flex min-w-0 items-center gap-2 overflow-visible text-muted" role="status" aria-live="polite">
    <span class="relative flex size-3 shrink-0 items-center justify-center overflow-visible" aria-hidden="true">
      <span class="absolute size-2.5 rounded-full bg-primary/30 animate-ping" />
      <span class="size-1.5 rounded-full bg-primary/80" />
    </span>
    <UChatShimmer :text="label" class="rainbow-chat-shimmer min-w-0 text-sm" />
  </div>
</template>
