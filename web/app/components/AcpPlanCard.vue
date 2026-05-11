<script setup lang="ts">
import type { PlanEntry } from '@agentclientprotocol/sdk'

const props = defineProps<{
  entries: PlanEntry[]
}>()

const completedCount = computed(() => props.entries.filter(entry => entry.status === 'completed').length)
const totalCount = computed(() => props.entries.length)
const activeEntry = computed(() => props.entries.find(entry => entry.status === 'in_progress') || null)
const summary = computed(() => {
  if (!totalCount.value) return 'No plan entries'
  const base = `${completedCount.value}/${totalCount.value} completed`
  return activeEntry.value ? `${base} · ${activeEntry.value.content}` : base
})

function statusIcon(status: PlanEntry['status']) {
  if (status === 'completed') return 'i-lucide-circle-check'
  if (status === 'in_progress') return 'i-lucide-loader-circle'
  return 'i-lucide-circle'
}

function statusColor(status: PlanEntry['status']) {
  if (status === 'completed') return 'text-success'
  if (status === 'in_progress') return 'text-primary'
  return 'text-dimmed'
}

function priorityColor(priority: PlanEntry['priority']) {
  if (priority === 'high') return 'error'
  if (priority === 'low') return 'neutral'
  return 'warning'
}
</script>

<template>
  <details class="group/plan rounded-xl border border-default bg-muted/20 text-sm" open>
    <summary class="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-muted transition-colors hover:text-default [&::-webkit-details-marker]:hidden">
      <UIcon
        name="i-lucide-chevron-right"
        class="size-3.5 shrink-0 text-dimmed transition-transform group-open/plan:rotate-90"
      />
      <UIcon name="i-lucide-list-checks" class="size-4 shrink-0 text-dimmed" />
      <span class="shrink-0 font-medium text-toned">Plan</span>
      <span class="min-w-0 truncate text-dimmed">{{ summary }}</span>
    </summary>

    <ol class="space-y-1 border-t border-default px-3 py-2">
      <li
        v-for="(entry, index) in entries"
        :key="`${index}:${entry.content}`"
        class="flex min-w-0 items-start gap-2 rounded-md px-1 py-1 text-muted"
      >
        <UIcon
          :name="statusIcon(entry.status)"
          class="mt-0.5 size-3.5 shrink-0"
          :class="[statusColor(entry.status), { 'animate-spin': entry.status === 'in_progress' }]"
        />
        <span
          class="min-w-0 flex-1 leading-5"
          :class="{ 'text-dimmed line-through decoration-muted': entry.status === 'completed', 'text-highlighted': entry.status === 'in_progress' }"
        >
          {{ entry.content }}
        </span>
        <UBadge
          :color="priorityColor(entry.priority)"
          variant="soft"
          size="sm"
          class="shrink-0 capitalize"
        >
          {{ entry.priority }}
        </UBadge>
      </li>
    </ol>
  </details>
</template>
