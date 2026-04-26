<script setup lang="ts">
import type { WebChatPart } from '~/types/web-chat'

const props = defineProps<{
  part: WebChatPart
}>()

type DetailSection = {
  label: string
  value: unknown
  text: string
}

const toolName = computed(() => props.part.name || 'Tool call')

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

function isPresent(value: unknown) {
  return value !== undefined && value !== null && value !== ''
}

const sections = computed<DetailSection[]>(() => {
  return [
    ['Input', props.part.input],
    ['Output', props.part.output]
  ]
    .filter(([, value]) => isPresent(value))
    .map(([label, value]) => ({
      label: String(label),
      value,
      text: formatValue(value)
    }))
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
  const output = props.part.output
  if (isPresent(output)) return valueSummary(output)

  const input = props.part.input
  if (isPresent(input)) return valueSummary(input)

  return props.part.status || 'Details'
})
</script>

<template>
  <UModal
    :title="toolName"
    :description="summary"
    scrollable
    :ui="{ content: 'sm:max-w-3xl', body: 'p-0' }"
  >
    <UButton
      type="button"
      color="neutral"
      variant="subtle"
      class="my-2 max-w-full justify-start overflow-hidden"
      leading-icon="i-lucide-terminal"
      trailing-icon="i-lucide-expand"
    >
      <span class="min-w-0 truncate text-left">{{ toolName }}</span>
      <span class="min-w-0 truncate text-muted">{{ summary }}</span>
    </UButton>

    <template #body>
      <div class="max-h-[70vh] overflow-y-auto p-4">
        <div v-if="sections.length" class="space-y-4">
          <section v-for="section in sections" :key="section.label" class="space-y-2">
            <div class="flex items-center justify-between gap-3">
              <h3 class="text-sm font-medium text-highlighted">
                {{ section.label }}
              </h3>
              <UBadge color="neutral" variant="soft" size="sm">
                {{ typeof normalizeValue(section.value) }}
              </UBadge>
            </div>
            <pre class="overflow-x-hidden rounded-md bg-muted p-3 text-xs leading-5 whitespace-pre-wrap break-words text-highlighted">{{ section.text }}</pre>
          </section>
        </div>

        <p v-else class="text-sm text-muted">
          No tool payload available.
        </p>
      </div>
    </template>
  </UModal>
</template>
