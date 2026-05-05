<script setup lang="ts">
import type { SkillFilePreviewRequest, WebChatFilePreview, WebChatPart } from '~/types/web-chat'
import type { ToolDetailSection } from '~/utils/toolCallDetails'
import { writeClipboardText } from '~/utils/clipboard'
import { toolCallTitle, toolDisplayInfo, toolOutputSummary } from '~/utils/toolCalls'
import { normalizeDetailValue, toolDetailOverview, toolDetailSections } from '~/utils/toolCallDetails'
import { formatProcessPartDuration } from '~/utils/chatMessages'

const props = defineProps<{
  part: WebChatPart
}>()

const toolInfo = computed(() => toolDisplayInfo(props.part))
const api = useHermesApi()
const toolName = computed(() => toolInfo.value.label)
const rawToolName = computed(() => toolInfo.value.rawName)
const isRunning = computed(() => ['running', 'thinking', 'streaming', 'started'].includes(String(props.part.status || '')))
const now = ref(new Date())
const open = ref(false)
const skillPreviewOpen = ref(false)
const skillPreviewLoading = ref(false)
const skillPreviewError = ref<string | null>(null)
const skillPreview = ref<WebChatFilePreview | null>(null)
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

function humanizeStatus(value?: string | null) {
  if (!value) return 'Completed'
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase())
}

const statusLabel = computed(() => isRunning.value ? 'Running' : humanizeStatus(props.part.status))
const secondarySummary = computed(() => {
  if (!summary.value || summary.value.toLowerCase() === statusLabel.value.toLowerCase()) return undefined
  return summary.value
})

const actionLabel = computed(() => toolCallTitle(props.part))
const isSkillView = computed(() => rawToolName.value.replace(/^functions\./, '') === 'skill_view')
const outputSkillPreview = computed(() => isSkillView.value ? createSkillPreview(props.part) : null)

async function openSkillPreview() {
  skillPreviewOpen.value = true
  skillPreviewError.value = null
  skillPreviewLoading.value = false

  const outputPreview = outputSkillPreview.value
  if (outputPreview) {
    skillPreview.value = outputPreview
    return
  }

  const request = skillPreviewRequest(props.part)
  if (!request) {
    skillPreview.value = null
    skillPreviewError.value = 'Skill name is not available in this tool call.'
    return
  }

  skillPreview.value = null
  skillPreviewLoading.value = true
  try {
    skillPreview.value = await api.fetchSkillFilePreview(request)
  } catch (err) {
    skillPreviewError.value = err instanceof Error ? err.message : 'Could not load skill file preview'
  } finally {
    skillPreviewLoading.value = false
  }
}

function skillPreviewRequest(part: WebChatPart): SkillFilePreviewRequest | null {
  const output = normalizeDetailValue(part.output)
  const outputRecord = isRecord(output) ? output : null
  const result = outputRecord ? normalizeDetailValue(outputRecord.result) : null
  const resultRecord = isRecord(result) ? result : null
  const args = skillInputArguments(part)

  const name = stringValue(args?.name)
    || stringValue(outputRecord?.name)
    || stringValue(outputRecord?.skill)
    || stringValue(resultRecord?.name)
    || stringValue(resultRecord?.skill)
  if (!name) return null

  const filePath = stringValue(args?.file_path)
    || stringValue(args?.filePath)
    || stringValue(outputRecord?.file_path)
    || stringValue(outputRecord?.filePath)
    || stringValue(resultRecord?.file_path)
    || stringValue(resultRecord?.filePath)
    || null

  return { name, filePath }
}

function skillInputArguments(part: WebChatPart): Record<string, unknown> | null {
  const input = normalizeDetailValue(part.input)
  if (!isRecord(input)) return null

  const directArgs = normalizeDetailValue(input.arguments)
  if (isRecord(directArgs)) return directArgs

  const functionValue = normalizeDetailValue(input.function)
  if (isRecord(functionValue)) {
    const functionArgs = normalizeDetailValue(functionValue.arguments)
    if (isRecord(functionArgs)) return functionArgs
  }

  return input
}

function createSkillPreview(part: WebChatPart): WebChatFilePreview | null {
  const output = normalizeDetailValue(part.output)
  if (!isRecord(output)) return null

  const content = skillContent(output)
  if (!content) return null
  const path = stringValue(output.path) || skillPreviewPath(output)
  const name = stringValue(output.file_path) || fileName(path) || 'SKILL.md'
  const isMarkdown = name.endsWith('.md') || path.endsWith('.md')

  return {
    path,
    requestedPath: path,
    relativePath: path,
    name,
    mediaType: isMarkdown ? 'text/markdown' : 'text/plain',
    size: content.length,
    language: isMarkdown ? 'markdown' : 'text',
    content,
    truncated: Boolean(output.truncated),
    previewable: true
  }
}

function skillContent(output: Record<string, unknown>) {
  const direct = stringValue(output.content)
  if (direct) return direct

  const result = normalizeDetailValue(output.result)
  if (isRecord(result)) return stringValue(result.content)

  return ''
}

function skillPreviewPath(output: Record<string, unknown>) {
  const skillName = stringValue(output.name) || stringValue(output.skill) || 'skill'
  const filePath = stringValue(output.file_path) || 'SKILL.md'
  return `${skillName}/${filePath}`
}

function fileName(path: string) {
  return path.split('/').filter(Boolean).pop() || ''
}

function stringValue(value: unknown) {
  return typeof value === 'string' && value.trim() ? value : ''
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}
</script>

<template>
  <button
    v-if="isSkillView"
    type="button"
    class="group flex w-full max-w-full items-center gap-1.5 overflow-hidden text-left text-sm text-muted transition-colors hover:text-default"
    @click="void openSkillPreview()"
  >
    <UIcon
      :name="isRunning ? 'i-lucide-cpu' : toolInfo.icon"
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

  <UModal
    v-else
    v-model:open="open"
    scrollable
    :ui="{ content: 'sm:max-w-2xl', header: 'hidden', body: 'p-0' }"
  >
    <button
      type="button"
      class="group flex w-full max-w-full items-center gap-1.5 overflow-hidden text-left text-sm text-muted transition-colors hover:text-default"
    >
      <UIcon
        :name="isRunning ? 'i-lucide-cpu' : toolInfo.icon"
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

  <ChatFilePreviewModal
    v-if="isSkillView"
    v-model:open="skillPreviewOpen"
    :preview="skillPreview"
    :loading="skillPreviewLoading"
    :error="skillPreviewError"
  />
</template>
