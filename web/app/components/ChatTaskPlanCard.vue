<script setup lang="ts">
import type { WebChatTaskPlan, WebChatTaskPlanItem, WebChatTaskPlanItemStatus } from '~/types/web-chat'

const props = defineProps<{
  taskPlan: WebChatTaskPlan
}>()

const statusMeta: Record<WebChatTaskPlanItemStatus, { icon: string, class: string, label: string }> = {
  pending: {
    icon: 'i-lucide-circle',
    class: 'text-dimmed',
    label: 'Pending'
  },
  in_progress: {
    icon: 'i-lucide-loader-circle',
    class: 'text-primary',
    label: 'In progress'
  },
  completed: {
    icon: 'i-lucide-circle-check',
    class: 'text-success',
    label: 'Completed'
  },
  cancelled: {
    icon: 'i-lucide-circle-minus',
    class: 'text-muted',
    label: 'Cancelled'
  }
}

const items = computed(() => props.taskPlan.items.filter(item => item.content.trim()))
const completedCount = computed(() => items.value.filter(item => item.status === 'completed').length)
const activeItem = computed(() => items.value.find(item => item.status === 'in_progress'))
const summary = computed(() => {
  if (!items.value.length) return 'No tasks'
  return `${completedCount.value}/${items.value.length} done`
})

function meta(item: WebChatTaskPlanItem) {
  return statusMeta[item.status] || statusMeta.pending
}
</script>

<template>
  <div v-if="items.length" class="rounded-md border border-default bg-default/60 px-2.5 py-2 shadow-xs">
    <div class="mb-2 flex items-center justify-between gap-3 text-xs">
      <div class="flex min-w-0 items-center gap-1.5 font-medium text-toned">
        <UIcon name="i-lucide-list-checks" class="size-3.5 shrink-0 text-dimmed" />
        <span class="shrink-0">Plan</span>
        <span v-if="activeItem" class="min-w-0 truncate font-normal text-muted">
          {{ activeItem.content }}
        </span>
      </div>
      <span class="shrink-0 text-dimmed">{{ summary }}</span>
    </div>

    <ol class="space-y-1">
      <li
        v-for="(item, index) in items"
        :key="item.id || index"
        class="grid grid-cols-[1.25rem_1fr] items-start gap-2 rounded px-1.5 py-1 text-sm leading-5"
        :class="item.status === 'in_progress' ? 'bg-primary/5' : ''"
      >
        <span class="relative mt-0.5 flex size-4 items-center justify-center text-[11px] tabular-nums text-dimmed">
          <span v-if="item.status === 'pending'">{{ index + 1 }}</span>
          <UIcon
            v-else
            :name="meta(item).icon"
            class="size-3.5"
            :class="[meta(item).class, item.status === 'in_progress' ? 'animate-spin' : '']"
            :aria-label="meta(item).label"
          />
        </span>
        <span
          class="min-w-0 text-toned"
          :class="item.status === 'completed' ? 'text-muted line-through decoration-muted/60' : ''"
        >
          {{ item.content }}
        </span>
      </li>
    </ol>
  </div>
</template>
