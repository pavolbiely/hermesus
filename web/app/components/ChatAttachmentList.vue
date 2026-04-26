<script setup lang="ts">
import type { WebChatAttachment } from '~/types/web-chat'

type ChatAttachmentListProps = {
  attachments?: WebChatAttachment[]
  disabled?: boolean
}

withDefaults(defineProps<ChatAttachmentListProps>(), {
  attachments: () => [],
  disabled: false
})

const emit = defineEmits<{
  remove: [id: string]
}>()
</script>

<template>
  <div v-if="attachments.length" class="flex min-w-0 flex-wrap gap-1.5 px-1">
    <UBadge
      v-for="attachment in attachments"
      :key="attachment.id"
      color="neutral"
      variant="soft"
      class="max-w-48 gap-1"
      :title="attachment.path"
    >
      <UIcon :name="attachment.mediaType.startsWith('image/') ? 'i-lucide-image' : 'i-lucide-file'" class="size-3.5 shrink-0" />
      <span class="truncate">{{ attachment.name }}</span>
      <UButton
        icon="i-lucide-x"
        color="neutral"
        variant="ghost"
        size="xs"
        :disabled="disabled"
        @click="emit('remove', attachment.id)"
      />
    </UBadge>
  </div>
</template>
