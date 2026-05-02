<script setup lang="ts">
import type { WebChatTaskPlan, WebChatTaskPlanItem, WebChatTaskPlanItemStatus } from '~/types/web-chat'

const props = defineProps<{
  taskPlan: WebChatTaskPlan
}>()

const expanded = ref(false)
const listRef = ref<HTMLElement | null>(null)

const statusMeta: Record<WebChatTaskPlanItemStatus, { icon: string, class: string, label: string }> = {
  pending: {
    icon: 'i-lucide-circle',
    class: 'text-dimmed',
    label: 'Pending'
  },
  in_progress: {
    icon: 'i-lucide-cpu',
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
const activeIndex = computed(() => items.value.findIndex(item => item.status === 'in_progress'))
const activeItem = computed(() => activeIndex.value >= 0 ? items.value[activeIndex.value] : null)
const summary = computed(() => {
  if (!items.value.length) return 'No tasks'
  return `${completedCount.value}/${items.value.length} done`
})
const hasScrollableList = computed(() => items.value.length > 5)
const visibleTitle = computed(() => activeItem.value?.content || items.value.find(item => item.status !== 'completed')?.content || items.value.at(-1)?.content || '')

function meta(item: WebChatTaskPlanItem) {
  return statusMeta[item.status] || statusMeta.pending
}

async function scrollToActiveTask() {
  if (!expanded.value || !hasScrollableList.value) return
  await nextTick()

  const list = listRef.value
  if (!list) return

  const index = activeIndex.value >= 0 ? activeIndex.value : 0
  const item = list.querySelector<HTMLElement>(`[data-task-index="${index}"]`)
  if (!item) {
    list.scrollTop = 0
    return
  }

  list.scrollTop = Math.max(0, item.offsetTop - 4)
}

watch(
  () => [props.taskPlan.updatedAt, activeIndex.value, items.value.length, expanded.value],
  () => void scrollToActiveTask(),
  { immediate: true }
)
</script>

<template>
  <div v-if="items.length" class="overflow-hidden rounded-t-lg border border-default bg-default/95 shadow-[0_-1px_8px_rgb(15_23_42/0.04)] backdrop-blur supports-[backdrop-filter]:bg-default/85">
    <button
      type="button"
      class="flex min-h-9 w-full items-center justify-between gap-3 px-3 py-2 text-left text-xs hover:bg-muted/40"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      <span class="flex min-w-0 items-center gap-2 font-medium text-toned">
        <UIcon name="i-lucide-list-checks" class="size-3.5 shrink-0 text-dimmed" />
        <span class="shrink-0">Plan</span>
        <span v-if="visibleTitle" class="min-w-0 truncate font-normal text-muted">
          {{ visibleTitle }}
        </span>
      </span>
      <span class="flex shrink-0 items-center gap-2 text-dimmed">
        <span>{{ summary }}</span>
        <UIcon name="i-lucide-chevron-down" class="size-3.5 transition-transform" :class="expanded ? 'rotate-180' : ''" />
      </span>
    </button>

    <div v-show="expanded" class="border-t border-default/70 px-2 py-1.5">
      <ol ref="listRef" class="space-y-1 overflow-y-auto pr-1" :class="hasScrollableList ? 'max-h-40' : ''">
        <li
          v-for="(item, index) in items"
          :key="item.id || index"
          :data-task-index="index"
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
  </div>
</template>
