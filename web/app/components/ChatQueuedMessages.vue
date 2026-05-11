<script setup lang="ts">
import type { QueuedMessage } from '~/utils/queuedMessages'

withDefaults(defineProps<{
  messages: QueuedMessage[]
  steeringId?: string | null
  disabled?: boolean
}>(), {
  steeringId: null,
  disabled: false
})

const emit = defineEmits<{
  edit: [id: string]
  delete: [id: string]
  steer: [id: string]
}>()

const iconButtonClass = 'size-7 rounded-md text-muted hover:text-toned hover:!bg-muted/60'
const iconClass = 'size-3.5'
</script>

<template>
  <div
    class="overflow-hidden rounded-xl border border-default bg-muted text-sm shadow-sm"
    aria-label="Queued messages"
  >
    <div
      v-for="(message, index) in messages"
      :key="message.id"
      class="flex min-h-10 items-center gap-2 px-3 py-2"
      :class="{ 'border-t border-default/60': index > 0 }"
    >
      <UIcon name="i-lucide-list-tree" class="size-4 shrink-0 text-dimmed" />

      <p class="min-w-0 flex-1 truncate whitespace-pre-wrap text-toned">
        {{ message.text }}
      </p>

      <div class="flex shrink-0 items-center gap-0.5">
        <UTooltip text="Steer current run" :content="{ side: 'top', sideOffset: 6 }">
          <UButton
            color="neutral"
            variant="ghost"
            size="xs"
            :icon="steeringId === message.id ? 'i-lucide-cpu' : 'i-lucide-corner-down-right'"
            label="Steer"
            loading-icon="i-lucide-cpu"
            :loading="steeringId === message.id"
            :ui="{ leadingIcon: iconClass }"
            class="h-7 rounded-md px-1.5 text-xs text-muted hover:text-toned hover:!bg-muted/60"
            aria-label="Steer current run"
            :disabled="disabled"
            @click="emit('steer', message.id)"
          />
        </UTooltip>

        <UTooltip text="Delete queued message" :content="{ side: 'top', sideOffset: 6 }">
          <UButton
            color="neutral"
            variant="ghost"
            size="xs"
            square
            icon="i-lucide-trash-2"
            :ui="{ leadingIcon: iconClass }"
            :class="iconButtonClass"
            aria-label="Delete queued message"
            :disabled="disabled || steeringId === message.id"
            @click="emit('delete', message.id)"
          />
        </UTooltip>

        <UTooltip text="Edit queued message" :content="{ side: 'top', sideOffset: 6 }">
          <UButton
            color="neutral"
            variant="ghost"
            size="xs"
            square
            icon="i-lucide-pencil"
            :ui="{ leadingIcon: iconClass }"
            :class="iconButtonClass"
            aria-label="Edit queued message"
            :disabled="disabled || steeringId === message.id"
            @click="emit('edit', message.id)"
          />
        </UTooltip>
      </div>
    </div>
  </div>
</template>
