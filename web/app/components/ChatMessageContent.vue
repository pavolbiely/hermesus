<script setup lang="ts">
import highlight from '@comark/nuxt/plugins/highlight'
import type { WebChatMessage } from '~/types/web-chat'
import { formatMessageTimestamp, groupMessageParts, messageTimestampTitle, partText } from '~/utils/chatMessages'

const editingText = defineModel<string>('editingText', { required: true })

defineProps<{
  message: WebChatMessage
  isThinking: boolean
  copiedMessageId: string | null
  editingMessageId: string | null
  savingEditedMessageId: string | null
  isRunning: boolean
  setEditingMessageContainer: (el: unknown) => void
}>()

const emit = defineEmits<{
  copy: [message: WebChatMessage]
  edit: [message: WebChatMessage]
  cancelEdit: []
  saveEdit: [message: WebChatMessage]
}>()
</script>

<template>
  <div v-if="isThinking" class="flex items-center gap-2 text-sm text-muted">
    <UIcon name="i-lucide-loader-circle" class="size-4 animate-spin" />
    <span>Thinking…</span>
  </div>

  <template v-for="(group, index) in groupMessageParts(message.parts)" :key="`${message.id}-${group.type}-${index}`">
    <div v-if="group.type === 'tools'" class="space-y-0.5">
      <ToolCallItem
        v-for="(toolPart, toolIndex) in group.parts"
        :key="`${message.id}-tool-${index}-${toolIndex}`"
        :part="toolPart"
      />
    </div>

    <template v-else>
      <UChatReasoning v-if="group.part.type === 'reasoning'" :text="partText(group.part)">
        <Comark :markdown="partText(group.part)" :plugins="[highlight()]" class="*:first:mt-0 *:last:mb-0" />
      </UChatReasoning>

      <div v-else-if="group.part.type === 'media' && group.part.attachments?.length" class="mb-2 flex flex-wrap gap-2">
        <ChatAttachmentPreview
          v-for="attachment in group.part.attachments"
          :key="attachment.id"
          :attachment="attachment"
        />
      </div>

      <ChatChangeSummary
        v-else-if="group.part.type === 'changes' && group.part.changes"
        :changes="group.part.changes"
      />

      <template v-else-if="group.part.type === 'text'">
        <Comark
          v-if="message.role === 'assistant'"
          :markdown="partText(group.part)"
          :plugins="[highlight()]"
          class="*:first:mt-0 *:last:mb-0"
        />
        <div v-else-if="editingMessageId === message.id" :ref="setEditingMessageContainer" class="space-y-2">
          <UTextarea
            v-model="editingText"
            autoresize
            :rows="3"
            class="w-full min-w-72"
            @keydown.esc.prevent="emit('cancelEdit')"
          />
          <div class="flex justify-end gap-2">
            <UButton
              size="xs"
              color="neutral"
              variant="ghost"
              label="Cancel"
              :disabled="savingEditedMessageId === message.id"
              @click="emit('cancelEdit')"
            />
            <UButton
              size="xs"
              color="primary"
              variant="soft"
              label="Save"
              :loading="savingEditedMessageId === message.id"
              :disabled="!editingText.trim()"
              @click="emit('saveEdit', message)"
            />
          </div>
        </div>
        <p v-else class="whitespace-pre-wrap">
          {{ partText(group.part) }}
        </p>
      </template>
    </template>
  </template>

  <div
    v-if="message.role === 'user'"
    class="pointer-events-none absolute -bottom-6 right-0 flex w-max max-w-none flex-nowrap items-center justify-end gap-1 whitespace-nowrap text-xs leading-4 text-muted opacity-0 transition-opacity group-hover/message:pointer-events-auto group-hover/message:opacity-100 group-focus-within/message:pointer-events-auto group-focus-within/message:opacity-100"
  >
    <span class="whitespace-nowrap" :title="messageTimestampTitle(message.createdAt)">
      {{ formatMessageTimestamp(message.createdAt) }}
    </span>
    <button
      type="button"
      class="inline-flex size-4 flex-none items-center justify-center text-muted hover:text-highlighted focus-visible:outline-2 focus-visible:outline-primary/50"
      aria-label="Edit message"
      :disabled="isRunning || savingEditedMessageId === message.id"
      @click="emit('edit', message)"
    >
      <UIcon name="i-lucide-pencil" class="size-3" />
    </button>
    <button
      type="button"
      class="inline-flex size-4 flex-none items-center justify-center text-muted hover:text-highlighted focus-visible:outline-2 focus-visible:outline-primary/50"
      :aria-label="copiedMessageId === message.id ? 'Copied message' : 'Copy message'"
      @click="emit('copy', message)"
    >
      <UIcon :name="copiedMessageId === message.id ? 'i-lucide-check' : 'i-lucide-copy'" class="size-3" />
    </button>
  </div>
</template>
