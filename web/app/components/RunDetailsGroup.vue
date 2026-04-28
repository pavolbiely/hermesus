<script setup lang="ts">
import highlight from '@comark/nuxt/plugins/highlight'
import type { WebChatPart } from '~/types/web-chat'
import { partText, processGroupSummary } from '~/utils/chatMessages'

const props = defineProps<{
  parts: WebChatPart[]
  expandedDefault?: boolean
}>()

const expanded = ref(props.expandedDefault === true)
const markdownPlugins = [highlight()]

watch(() => props.expandedDefault, value => {
  expanded.value = value === true
})

const summary = computed(() => processGroupSummary(props.parts))
const hasFailure = computed(() => summary.value.includes('failed'))

function isStreamingReasoning(part: WebChatPart) {
  return part.type === 'reasoning' && part.status === 'streaming'
}

function reasoningDurationSeconds(part: WebChatPart) {
  if (typeof part.durationMs !== 'number' || !Number.isFinite(part.durationMs)) return undefined
  return Math.max(1, Math.round(part.durationMs / 1000))
}
</script>

<template>
  <section class="rounded-lg border border-default bg-muted/20 text-sm">
    <button
      type="button"
      class="flex w-full items-center gap-2 overflow-hidden px-3 py-2 text-left text-muted transition-colors hover:text-default"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      <UIcon
        :name="expanded ? 'i-lucide-chevron-down' : 'i-lucide-chevron-right'"
        class="size-3.5 shrink-0 text-dimmed"
      />
      <UIcon
        :name="hasFailure ? 'i-lucide-circle-alert' : 'i-lucide-list-tree'"
        class="size-3.5 shrink-0"
        :class="hasFailure ? 'text-error' : 'text-dimmed'"
      />
      <span class="shrink-0 font-medium text-toned">
        Run details
      </span>
      <span v-if="summary" class="min-w-0 truncate text-dimmed">
        {{ summary }}
      </span>
    </button>

    <div v-if="expanded" class="space-y-1 border-t border-default px-3 py-2">
      <template v-for="(part, index) in parts" :key="`${part.type}-${part.name || index}-${index}`">
        <UChatReasoning
          v-if="part.type === 'reasoning'"
          :text="partText(part)"
          :streaming="isStreamingReasoning(part)"
          :duration="reasoningDurationSeconds(part)"
        >
          <Comark :markdown="partText(part)" :plugins="markdownPlugins" class="*:first:mt-0 *:last:mb-0" />
        </UChatReasoning>

        <ToolCallItem v-else-if="part.type === 'tool'" :part="part" />

        <div
          v-else-if="part.type === 'status'"
          class="flex items-start gap-2 rounded-md px-2 py-1 text-xs"
          :class="part.status === 'warn' ? 'bg-warning/10 text-warning' : 'bg-muted/30 text-muted'"
        >
          <UIcon
            :name="part.status === 'warn' ? 'i-lucide-triangle-alert' : 'i-lucide-info'"
            class="mt-0.5 size-3.5 shrink-0"
          />
          <span class="whitespace-pre-wrap text-toned">{{ partText(part) }}</span>
        </div>
      </template>
    </div>
  </section>
</template>
