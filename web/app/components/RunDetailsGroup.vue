<script setup lang="ts">
import highlight from '@comark/nuxt/plugins/highlight'
import type { WebChatPart } from '~/types/web-chat'
import { partText, processGroupSummary } from '~/utils/chatMessages'

const props = defineProps<{
  parts: WebChatPart[]
  expandedDefault?: boolean
}>()

const expanded = ref(props.expandedDefault === true)

watch(() => props.expandedDefault, value => {
  expanded.value = value === true
})

const summary = computed(() => processGroupSummary(props.parts))
const hasFailure = computed(() => summary.value.includes('failed'))
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
        <UChatReasoning v-if="part.type === 'reasoning'" :text="partText(part)">
          <Comark :markdown="partText(part)" :plugins="[highlight()]" class="*:first:mt-0 *:last:mb-0" />
        </UChatReasoning>

        <ToolCallItem v-else-if="part.type === 'tool'" :part="part" />
      </template>
    </div>
  </section>
</template>
