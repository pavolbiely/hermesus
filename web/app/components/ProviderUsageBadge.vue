<script setup lang="ts">
import type { WebChatProviderUsageResponse, WebChatProviderUsageWindow } from '~/types/web-chat'

const props = defineProps<{
  usage?: WebChatProviderUsageResponse | null
  loading?: boolean
  display?: 'badge' | 'text'
}>()

const primaryLimit = computed(() => props.usage?.limits.find(limit => limit.id === 'codex') || props.usage?.limits[0] || null)
const summaryWindows = computed(() => primaryLimit.value?.windows.slice(0, 2) || [])
const visibleLimits = computed(() => props.usage?.limits.filter(limit => limit.windows.length > 0) || [])
const hasUsageSummary = computed(() => Boolean(props.usage?.available && summaryWindows.value.length > 0))
const visible = computed(() => props.loading || hasUsageSummary.value)

const color = computed(() => {
  if (!props.usage?.available && !props.loading) return 'warning'
  const highestUsedPercent = Math.max(...summaryWindows.value.map(window => window.usedPercent), 0)
  if (highestUsedPercent >= 90) return 'warning'
  return 'info'
})

const badgeLabel = computed(() => {
  if (hasUsageSummary.value) {
    const parts = summaryWindows.value.map(window => `${formatPercent(window.remainingPercent)}${windowCode(window)}`)
    return `Codex ${parts.join(' · ')}`
  }

  return props.loading ? 'Codex…' : 'Codex limits unavailable'
})

function formatPercent(value: number) {
  const rounded = Math.round(value)
  return `${rounded}%`
}

function formatReset(value: string | null | undefined) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat(undefined, {
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date)
}

function windowCode(window: WebChatProviderUsageWindow) {
  const label = window.label.toLowerCase()
  if (label.startsWith('daily')) return 'D'
  if (label.startsWith('weekly')) return 'W'
  if (label.endsWith('h')) return label
  if (label.endsWith('m')) return label
  return label.slice(0, 1).toUpperCase()
}

</script>

<template>
  <div v-if="visible && display === 'text'" class="inline-flex items-center justify-center gap-1.5 text-[11px] leading-4 text-muted">
    <span>{{ badgeLabel }}</span>
    <UPopover
      :content="{ side: 'top', align: 'center', sideOffset: 8 }"
      :ui="{ content: 'w-80 p-0' }"
    >
      <button
        type="button"
        aria-label="Show provider usage details"
        class="inline-flex size-3.5 items-center justify-center rounded-full text-muted transition-colors hover:text-toned focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      >
        <UIcon name="i-lucide-info" class="size-3" />
      </button>

      <template #content>
        <div class="w-80 space-y-3 p-3 text-left text-xs leading-relaxed">
          <div class="flex items-center justify-between gap-3 border-b border-default pb-2">
            <div class="font-medium text-highlighted">Codex limits</div>
            <div class="text-muted">refreshes every 5m</div>
          </div>

          <div v-if="loading" class="text-muted">Loading provider usage…</div>

          <div v-else class="space-y-3">
            <div
              v-for="limit in visibleLimits"
              :key="limit.id"
              class="space-y-2"
            >
              <div class="font-medium text-highlighted">{{ limit.label }}</div>

              <div class="space-y-2">
                <div
                  v-for="window in limit.windows"
                  :key="`${limit.id}-${window.label}`"
                  class="grid grid-cols-[4rem_1fr] gap-3 rounded-md border border-default/70 bg-muted/80 p-2 dark:bg-muted/40"
                >
                  <div class="font-medium text-highlighted">{{ window.label }}</div>
                  <div class="min-w-0 space-y-1">
                    <div class="flex justify-between gap-3">
                      <span class="text-muted">Remaining</span>
                      <span class="font-medium text-highlighted">{{ formatPercent(window.remainingPercent) }}</span>
                    </div>
                    <div class="flex justify-between gap-3">
                      <span class="text-muted">Used</span>
                      <span>{{ formatPercent(window.usedPercent) }}</span>
                    </div>
                    <div v-if="formatReset(window.resetsAt)" class="flex justify-between gap-3">
                      <span class="text-muted">Resets</span>
                      <span class="text-right">{{ formatReset(window.resetsAt) }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </UPopover>
  </div>

  <UPopover
    v-else-if="visible"
    mode="hover"
    :content="{ side: 'bottom', align: 'end', sideOffset: 8 }"
    :ui="{ content: 'w-80 p-0' }"
  >
    <UBadge
      :color="color"
      variant="subtle"
      icon="i-lucide-gauge"
      size="sm"
      class="hidden max-w-40 cursor-default truncate font-normal sm:inline-flex"
    >
      {{ badgeLabel }}
    </UBadge>

    <template #content>
      <div class="w-80 space-y-3 p-3 text-left text-xs leading-relaxed">
        <div class="flex items-center justify-between gap-3 border-b border-default pb-2">
          <div class="font-medium text-highlighted">Codex limits</div>
          <div class="text-muted">refreshes every 5m</div>
        </div>

        <div v-if="loading" class="text-muted">Loading provider usage…</div>

        <div v-else class="space-y-3">
          <div
            v-for="limit in visibleLimits"
            :key="limit.id"
            class="space-y-2"
          >
            <div class="font-medium text-highlighted">{{ limit.label }}</div>

            <div class="space-y-2">
              <div
                v-for="window in limit.windows"
                :key="`${limit.id}-${window.label}`"
                class="grid grid-cols-[4rem_1fr] gap-3 rounded-md border border-default/70 bg-muted/80 p-2 dark:bg-muted/40"
              >
                <div class="font-medium text-highlighted">{{ window.label }}</div>
                <div class="min-w-0 space-y-1">
                  <div class="flex justify-between gap-3">
                    <span class="text-muted">Remaining</span>
                    <span class="font-medium text-highlighted">{{ formatPercent(window.remainingPercent) }}</span>
                  </div>
                  <div class="flex justify-between gap-3">
                    <span class="text-muted">Used</span>
                    <span>{{ formatPercent(window.usedPercent) }}</span>
                  </div>
                  <div v-if="formatReset(window.resetsAt)" class="flex justify-between gap-3">
                    <span class="text-muted">Resets</span>
                    <span class="text-right">{{ formatReset(window.resetsAt) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </UPopover>
</template>
