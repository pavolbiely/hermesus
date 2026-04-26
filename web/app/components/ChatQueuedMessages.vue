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

      <div class="flex shrink-0 items-center gap-1 pt-0.5">
        <UButton
          color="neutral"
          variant="ghost"
          size="xs"
          icon="i-lucide-pencil"
          aria-label="Edit queued message"
          :disabled="disabled || steeringId === message.id"
          @click="emit('edit', message.id)"
        />
        <UButton
          color="neutral"
          variant="ghost"
          size="xs"
          :icon="steeringId === message.id ? 'i-lucide-loader-circle' : 'i-lucide-send'"
          :loading="steeringId === message.id"
          aria-label="Steer current run"
          :disabled="disabled"
          @click="emit('steer', message.id)"
        />
        <UButton
          color="neutral"
          variant="ghost"
          size="xs"
          icon="i-lucide-trash-2"
          aria-label="Delete queued message"
          :disabled="disabled || steeringId === message.id"
          @click="emit('delete', message.id)"
        />
      </div>
    </div>
  </div>
</template>
