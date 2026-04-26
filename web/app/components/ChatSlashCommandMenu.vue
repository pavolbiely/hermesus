<script setup lang="ts">
import type { WebChatCommand } from '~/types/web-chat'

type ChatSlashCommandMenuProps = {
  commands?: WebChatCommand[]
  open?: boolean
  loading?: boolean
  highlightedIndex?: number
}

withDefaults(defineProps<ChatSlashCommandMenuProps>(), {
  commands: () => [],
  open: false,
  loading: false,
  highlightedIndex: 0
})

const emit = defineEmits<{
  select: [command: WebChatCommand]
  highlight: [index: number]
}>()
</script>

<template>
  <div
    v-if="open"
    class="absolute inset-x-0 bottom-full z-30 mb-2 max-h-56 overflow-y-auto rounded-lg border border-default bg-default p-1 shadow-xl"
  >
    <div v-if="loading" class="flex items-center gap-2 px-2 py-1.5 text-sm text-muted">
      <UIcon name="i-lucide-loader-circle" class="size-4 animate-spin" />
      <span>Loading commands…</span>
    </div>
    <template v-else>
      <button
        v-for="(command, index) in commands"
        :key="command.id"
        type="button"
        class="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-elevated"
        :class="index === highlightedIndex ? 'bg-elevated' : undefined"
        @mouseenter="emit('highlight', index)"
        @mousedown.prevent="emit('select', command)"
      >
        <UIcon name="i-lucide-terminal" class="mt-0.5 size-4 shrink-0 text-muted" />
        <span class="min-w-0 flex-1">
          <span class="block font-medium text-highlighted">{{ command.name }}</span>
          <span class="block truncate text-muted">{{ command.description }}</span>
        </span>
        <UBadge
          v-if="command.safety !== 'safe'"
          size="sm"
          color="warning"
          variant="soft"
        >
          Confirm
        </UBadge>
      </button>
    </template>
  </div>
</template>
