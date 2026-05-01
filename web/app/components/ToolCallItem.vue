<script setup lang="ts">
import type { WebChatPart } from '~/types/web-chat'
import type { ToolDetailSection } from '~/utils/toolCallDetails'
import { writeClipboardText } from '~/utils/clipboard'
import { toolCallTitle, toolDisplayInfo, toolOutputSummary } from '~/utils/toolCalls'
import { toolDetailOverview, toolDetailSections } from '~/utils/toolCallDetails'
import { formatProcessPartDuration } from '~/utils/chatMessages'

const props = defineProps<{
  part: WebChatPart
}>()

const toolInfo = computed(() => toolDisplayInfo(props.part))
const toolName = computed(() => toolInfo.value.label)
const rawToolName = computed(() => toolInfo.value.rawName)
const isRunning = computed(() => ['running', 'thinking', 'streaming', 'started'].includes(String(props.part.status || '')))
const now = ref(new Date())
const open = ref(false)
const rawOpen = ref(false)
const copiedSection = ref<string | null>(null)
const wrappedSections = ref<Record<string, boolean>>({})
let copiedTimer: ReturnType<typeof setTimeout> | undefined
let durationTimer: ReturnType<typeof setInterval> | undefined

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

onMounted(() => {
  durationTimer = setInterval(() => {
    if (isRunning.value) now.value = new Date()
  }, 1000)
})

onBeforeUnmount(() => {
  if (copiedTimer) clearTimeout(copiedTimer)
  if (durationTimer) clearInterval(durationTimer)
})

const durationLabel = computed(() => formatProcessPartDuration(props.part, now.value))
const sections = computed(() => toolDetailSections(props.part))
const overview = computed(() => toolDetailOverview({
  ...props.part,
  name: toolName.value
}))

const summary = computed(() => {
  if (isRunning.value) return 'Running'
  return toolOutputSummary(props.part)
})

const statusLabel = computed(() => isRunning.value ? 'Running' : (props.part.status || 'Completed'))
const secondarySummary = computed(() => {
  if (!summary.value || summary.value.toLowerCase() === statusLabel.value.toLowerCase()) return undefined
  return summary.value
})

const actionLabel = computed(() => toolCallTitle(props.part))
</script>

<template>
  <UModal
    v-model:open="open"
    scrollable
    :ui="{ content: 'sm:max-w-2xl', header: 'hidden', body: 'p-0' }"
  >
    <button
      type="button"
      class="group flex w-full max-w-full items-center gap-1.5 overflow-hidden text-left text-sm text-muted transition-colors hover:text-default"
    >
      <UIcon
        :name="isRunning ? 'i-lucide-loader-circle' : toolInfo.icon"
        class="size-3.5 shrink-0 text-dimmed"
        :class="{ 'animate-spin': isRunning }"
      />
      <span class="min-w-0 truncate" :class="{ 'tool-call-shimmer': isRunning }">
        {{ actionLabel }}
      </span>
      <span v-if="summary" class="min-w-0 truncate text-dimmed" :class="{ 'tool-call-shimmer': isRunning }">
        {{ summary }}
      </span>
      <span
        v-if="durationLabel"
        class="ml-auto inline-flex shrink-0 items-center gap-1 rounded-full bg-muted/50 px-1.5 py-0.5 font-mono text-[11px] leading-none text-dimmed tabular-nums"
        :title="isRunning ? 'Elapsed time' : 'Duration'"
      >
        <span v-if="isRunning" class="size-1.5 rounded-full bg-primary/70 animate-pulse" aria-hidden="true" />
        {{ durationLabel }}
      </span>
    </button>

    <template #body>
      <div class="relative max-h-[60vh] overflow-y-auto p-2 text-xs">
        <UButton
          color="neutral"
          variant="ghost"
          size="xs"
          icon="i-lucide-x"
          aria-label="Close"
          class="absolute right-1.5 top-1.5 z-10"
          @click="open = false"
        />

        <div class="mb-2 flex min-w-0 items-center gap-2 pr-8">
          <UBadge :color="isRunning ? 'primary' : 'neutral'" variant="soft" size="sm">
            {{ statusLabel }}
          </UBadge>
          <UBadge color="neutral" variant="subtle" size="sm">
            {{ toolInfo.category }}
          </UBadge>
          <span class="inline-flex min-w-0 items-center gap-1 text-muted">
            <UIcon :name="toolInfo.icon" class="size-3.5 shrink-0 text-dimmed" />
            <span class="truncate">{{ toolName }}</span>
          </span>
          <span class="shrink-0 rounded bg-muted/60 px-1 py-0.5 font-mono text-[11px] text-dimmed" :title="rawToolName">
            {{ rawToolName }}
          </span>
          <span v-if="durationLabel" class="ml-auto font-mono text-dimmed tabular-nums">
            {{ durationLabel }}
          </span>
          <span v-if="secondarySummary" class="min-w-0 truncate text-muted">
            {{ secondarySummary }}
          </span>
        </div>

        <section v-if="overview.inputFields.length" class="border-t border-default py-1.5">
          <h3 class="mb-1 text-[11px] font-medium uppercase tracking-wide text-dimmed">
            Input
          </h3>
          <dl class="divide-y divide-default/60">
            <div v-for="field in overview.inputFields" :key="field.label" class="grid grid-cols-[7rem_minmax(0,1fr)] gap-2 py-1">
              <dt class="truncate text-dimmed">
                {{ field.label }}
              </dt>
              <dd class="min-w-0 truncate text-highlighted" :class="{ 'font-mono': field.code }" :title="field.value">
                {{ field.value }}
              </dd>
            </div>
          </dl>
        </section>

        <section v-if="overview.resultFields.length" class="border-t border-default py-1.5">
          <h3 class="mb-1 text-[11px] font-medium uppercase tracking-wide text-dimmed">
            Result
          </h3>
          <dl class="divide-y divide-default/60">
            <div v-for="field in overview.resultFields" :key="field.label" class="grid grid-cols-[7rem_minmax(0,1fr)] gap-2 py-1">
              <dt class="truncate text-dimmed">
                {{ field.label }}
              </dt>
              <dd class="min-w-0 truncate text-highlighted" :class="{ 'font-mono': field.code }" :title="field.value">
                {{ field.value }}
              </dd>
            </div>
          </dl>
        </section>

        <section v-if="overview.blocks.length" class="border-t border-default py-1.5">
          <UCollapsible v-for="block in overview.blocks" :key="block.label">
            <UButton
              color="neutral"
              variant="ghost"
              size="xs"
              trailing-icon="i-lucide-chevron-down"
              :label="block.label"
              class="-mx-1"
            />
            <template #content>
              <pre class="mt-1 max-h-48 overflow-auto rounded-md bg-muted/50 p-2 text-xs leading-5 text-highlighted" :class="block.kind === 'code' ? 'font-mono' : 'whitespace-pre-wrap'">{{ block.value }}</pre>
            </template>
          </UCollapsible>
        </section>

        <UCollapsible v-if="sections.length" v-model:open="rawOpen" class="border-t border-default pt-1.5">
          <UButton
            color="neutral"
            variant="ghost"
            size="xs"
            :trailing-icon="rawOpen ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
            label="Raw"
            class="-mx-1"
          />
          <template #content>
            <div class="mt-2 grid gap-2">
              <ToolCallDetailSection
                v-for="section in sections"
                :key="section.label"
                :section="section"
                :path="`${toolName}-${section.label}`"
                :copied="copiedSection === section.label"
                :wrapped="isWrapped(section.label)"
                :single="true"
                @copy="copySection"
                @toggle-wrap="toggleWrap"
              />
            </div>
          </template>
        </UCollapsible>
      </div>
    </template>
  </UModal>
</template>
