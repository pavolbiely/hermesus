<script setup lang="ts">
import type { WebChatPart } from '~/types/web-chat'
import type { ToolDetailSection } from '~/utils/toolCallDetails'
import { writeClipboardText } from '~/utils/clipboard'
import { toolDisplayName } from '~/utils/toolCalls'
import { hasDetailValue, toolDetailSections, valueSummary } from '~/utils/toolCallDetails'

const props = defineProps<{
  part: WebChatPart
}>()

const toolName = computed(() => toolDisplayName(props.part))
const isRunning = computed(() => ['running', 'thinking', 'streaming', 'started'].includes(String(props.part.status || '')))
const copiedSection = ref<string | null>(null)
const wrappedSections = ref<Record<string, boolean>>({})
let copiedTimer: ReturnType<typeof setTimeout> | undefined

function isWrapped(label: string) {
  return wrappedSections.value[label] === true
}

function toggleWrap(label: string) {
  wrappedSections.value = {
    ...wrappedSections.value,
    [label]: !isWrapped(label)
  }
}

async function copySection(section: ToolDetailSection) {
  await writeClipboardText(section.text)
  copiedSection.value = section.label

  if (copiedTimer) clearTimeout(copiedTimer)
  copiedTimer = setTimeout(() => {
    copiedSection.value = null
  }, 1600)
}

onBeforeUnmount(() => {
  if (copiedTimer) clearTimeout(copiedTimer)
})

const sections = computed(() => toolDetailSections(props.part))

const summary = computed(() => {
  if (isRunning.value) return valueSummary(props.part.input) || 'Running'

  const output = props.part.output
  if (hasDetailValue(output)) return valueSummary(output)

  const input = props.part.input
  if (hasDetailValue(input)) return valueSummary(input)

  return props.part.status || 'Details'
})

const actionLabel = computed(() => `${isRunning.value ? 'Running' : 'Ran'} ${toolName.value}`)
</script>

<template>
  <UModal
    :title="toolName"
    :description="summary"
    scrollable
    :ui="{ content: 'sm:max-w-7xl', body: 'p-0' }"
  >
    <button
      type="button"
      class="group flex max-w-full items-center gap-1.5 overflow-hidden text-left text-sm text-muted transition-colors hover:text-default"
    >
      <UIcon
        :name="isRunning ? 'i-lucide-loader-circle' : 'i-lucide-chevron-down'"
        class="size-3.5 shrink-0 text-dimmed"
        :class="{ 'animate-spin': isRunning }"
      />
      <span class="min-w-0 truncate" :class="{ 'tool-call-shimmer': isRunning }">
        {{ actionLabel }}
      </span>
      <span v-if="summary" class="min-w-0 truncate text-dimmed" :class="{ 'tool-call-shimmer': isRunning }">
        {{ summary }}
      </span>
    </button>

    <template #body>
      <div class="h-[75vh] overflow-y-auto p-4 lg:overflow-hidden">
        <div v-if="sections.length" class="grid min-h-0 gap-4 lg:h-full lg:grid-cols-2 lg:auto-rows-fr">
          <ToolCallDetailSection
            v-for="section in sections"
            :key="section.label"
            :section="section"
            :path="`${toolName}-${section.label}`"
            :copied="copiedSection === section.label"
            :wrapped="isWrapped(section.label)"
            :single="sections.length === 1"
            @copy="copySection"
            @toggle-wrap="toggleWrap"
          />
        </div>

        <p v-else class="text-sm text-muted">
          No tool payload available.
        </p>
      </div>
    </template>
  </UModal>
</template>
