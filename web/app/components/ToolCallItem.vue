<script setup lang="ts">
import type { WebChatPart } from '~/types/web-chat'

const props = defineProps<{
  part: WebChatPart
}>()

type DetailSection = {
  label: string
  value: unknown
  text: string
  type: string
}

const toolName = computed(() => props.part.name || 'Tool call')
const isRunning = computed(() => ['running', 'thinking', 'streaming', 'started'].includes(String(props.part.status || '')))
const copiedSection = ref<string | null>(null)
const wrappedSections = ref<Record<string, boolean>>({})
let copiedTimer: ReturnType<typeof setTimeout> | undefined

function normalizeValue(value: unknown) {
  if (typeof value !== 'string') return value

  const trimmed = value.trim()
  if (!trimmed || !['{', '['].includes(trimmed[0] || '')) return value

  try {
    return JSON.parse(trimmed)
  } catch {
    return value
  }
}

function formatValue(value: unknown) {
  const normalized = normalizeValue(value)

  if (typeof normalized === 'string') return normalized
  if (normalized === undefined) return ''

  return JSON.stringify(normalized, null, 2)
}

function valueType(value: unknown) {
  const normalized = normalizeValue(value)
  if (Array.isArray(normalized)) return 'array'
  if (normalized === null) return 'null'
  return typeof normalized
}

function isPresent(value: unknown) {
  return value !== undefined && value !== null && value !== ''
}

function isWrapped(label: string) {
  return wrappedSections.value[label] === true
}

function toggleWrap(label: string) {
  wrappedSections.value = {
    ...wrappedSections.value,
    [label]: !isWrapped(label)
  }
}

async function writeClipboardText(text: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()

  try {
    document.execCommand('copy')
  } finally {
    document.body.removeChild(textarea)
  }
}

async function copySection(section: DetailSection) {
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

const sections = computed<DetailSection[]>(() => {
  return [
    ['Input', props.part.input],
    ['Output', props.part.output]
  ]
    .filter(([, value]) => isPresent(value))
    .map(([label, value]) => {
      const text = formatValue(value)
      return {
        label: String(label),
        value,
        text,
        type: valueType(value)
      }
    })
})

function valueSummary(value: unknown) {
  const normalized = normalizeValue(value)

  if (Array.isArray(normalized)) return `${normalized.length} items`
  if (normalized && typeof normalized === 'object') {
    const record = normalized as Record<string, unknown>
    const parts: string[] = []

    if (typeof record.total_count === 'number') parts.push(`${record.total_count} total`)
    if (Array.isArray(record.files)) parts.push(`${record.files.length} files`)
    if (Array.isArray(record.items)) parts.push(`${record.items.length} items`)
    if (Array.isArray(record.results)) parts.push(`${record.results.length} results`)

    return parts.length ? parts.join(' · ') : `${Object.keys(record).length} keys`
  }

  const text = String(normalized ?? '').replace(/\s+/g, ' ').trim()
  return text.length > 56 ? `${text.slice(0, 56)}...` : text
}

const summary = computed(() => {
  if (isRunning.value) return valueSummary(props.part.input) || 'Running'

  const output = props.part.output
  if (isPresent(output)) return valueSummary(output)

  const input = props.part.input
  if (isPresent(input)) return valueSummary(input)

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
          <section
            v-for="section in sections"
            :key="section.label"
            class="flex min-h-0 max-h-full flex-col overflow-hidden rounded-lg border border-default bg-muted/40"
            :class="{ 'lg:col-span-2': sections.length === 1 }"
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
                  :icon="isWrapped(section.label) ? 'i-lucide-wrap-text' : 'i-lucide-arrow-left-right'"
                  :aria-label="isWrapped(section.label) ? `Use horizontal scroll for ${section.label}` : `Wrap ${section.label}`"
                  @click="toggleWrap(section.label)"
                />
                <UButton
                  size="xs"
                  color="neutral"
                  variant="ghost"
                  :icon="copiedSection === section.label ? 'i-lucide-check' : 'i-lucide-copy'"
                  :aria-label="copiedSection === section.label ? `Copied ${section.label}` : `Copy ${section.label}`"
                  @click="copySection(section)"
                />
              </div>
            </div>
            <div
              class="min-h-0 flex-1 overflow-y-auto p-3"
              :class="isWrapped(section.label) ? 'overflow-x-hidden' : 'overflow-x-auto'"
            >
              <JsonTree
                :value="section.value"
                :path="`${toolName}-${section.label}`"
                :default-expanded-depth="3"
                :wrap-lines="isWrapped(section.label)"
              />
            </div>
          </section>
        </div>

        <p v-else class="text-sm text-muted">
          No tool payload available.
        </p>
      </div>
    </template>
  </UModal>
</template>
