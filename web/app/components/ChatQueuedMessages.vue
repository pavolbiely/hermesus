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

const actionButtonClass = 'size-6 rounded-md'
const actionIconClass = 'size-3.5'
</script>

<template>
  <div class="space-y-2" aria-label="Queued messages">
    <div
      v-for="message in messages"
      :key="message.id"
      class="flex items-start gap-3 rounded-xl border border-default bg-muted/30 px-3 py-2 text-sm shadow-sm backdrop-blur"
    >
      <div class="min-w-0 flex-1 space-y-1">
        <UBadge color="neutral" variant="soft" size="sm" label="Queued" />
        <p class="line-clamp-3 whitespace-pre-wrap text-toned">
          {{ message.text }}
        </p>
      </div>

      <div class="flex shrink-0 items-center gap-0.5 pt-0.5">
        <UTooltip text="Steer current run" :content="{ side: 'top', sideOffset: 6 }">
          <UButton
            color="neutral"
            variant="ghost"
            size="xs"
            square
            :icon="steeringId === message.id ? 'i-lucide-cpu' : 'i-lucide-ship-wheel'"
            loading-icon="i-lucide-cpu"
            :loading="steeringId === message.id"
            :ui="{ leadingIcon: actionIconClass }"
            :class="actionButtonClass"
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
            :ui="{ leadingIcon: actionIconClass }"
            :class="actionButtonClass"
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
            :ui="{ leadingIcon: actionIconClass }"
            :class="actionButtonClass"
            aria-label="Edit queued message"
            :disabled="disabled || steeringId === message.id"
            @click="emit('edit', message.id)"
          />
        </UTooltip>
      </div>
    </div>
  </div>
</template>
