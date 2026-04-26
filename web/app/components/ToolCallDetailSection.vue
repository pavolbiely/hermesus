<script setup lang="ts">
import type { ToolDetailSection } from '~/utils/toolCallDetails'

const props = defineProps<{
  section: ToolDetailSection
  path: string
  copied: boolean
  wrapped: boolean
  single: boolean
}>()

const emit = defineEmits<{
  copy: [section: ToolDetailSection]
  toggleWrap: [label: string]
}>()
</script>

<template>
  <section
    class="flex min-h-0 max-h-full flex-col overflow-hidden rounded-lg border border-default bg-muted/40"
    :class="{ 'lg:col-span-2': props.single }"
  >
    <div class="flex items-center justify-between gap-3 border-b border-default px-3 py-2">
      <div class="flex min-w-0 items-center gap-2">
        <h3 class="truncate text-sm font-medium text-highlighted">
          {{ section.label }}
        </h3>
        <UBadge color="neutral" variant="soft" size="sm">
          {{ section.type }}
        </UBadge>
      </div>
      <div class="flex shrink-0 items-center gap-1">
        <UButton
          size="xs"
          color="neutral"
          variant="ghost"
          :icon="wrapped ? 'i-lucide-wrap-text' : 'i-lucide-arrow-left-right'"
          :aria-label="wrapped ? `Use horizontal scroll for ${section.label}` : `Wrap ${section.label}`"
          @click="emit('toggleWrap', section.label)"
        />
        <UButton
          size="xs"
          color="neutral"
          variant="ghost"
          :icon="copied ? 'i-lucide-check' : 'i-lucide-copy'"
          :aria-label="copied ? `Copied ${section.label}` : `Copy ${section.label}`"
          @click="emit('copy', section)"
        />
      </div>
    </div>
    <div
      class="min-h-0 flex-1 overflow-y-auto p-3"
      :class="wrapped ? 'overflow-x-hidden' : 'overflow-x-auto'"
    >
      <JsonTree
        :value="section.value"
        :path="path"
        :default-expanded-depth="3"
        :wrap-lines="wrapped"
      />
    </div>
  </section>
</template>
