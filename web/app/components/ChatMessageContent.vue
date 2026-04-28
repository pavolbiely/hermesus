<script setup lang="ts">
import highlight from '@comark/nuxt/plugins/highlight'
import type { WebChatMessage, WebChatPart } from '~/types/web-chat'
import { formatMessageGenerationDuration, formatMessageTimestamp, formatMessageTokenCount, groupMessageParts, messageDurationDetails, messagePartKey, messageTimestampTitle, messageTokenDetails, messageTokenTooltipNote, partText } from '~/utils/chatMessages'

const editingText = defineModel<string>('editingText', { required: true })
const openTooltipKey = ref<string | null>(null)

const tooltipContent = { side: 'top' as const, sideOffset: 8 }
const richTooltipUi = {
  content: 'h-auto max-w-none items-stretch rounded-md bg-elevated px-3 py-2 text-default shadow-lg ring ring-default'
}

const props = defineProps<{
  message: WebChatMessage
  copiedMessageId: string | null
  editingMessageId: string | null
  savingEditedMessageId: string | null
  isRunning: boolean
  setEditingMessageContainer: (el: unknown) => void
  latestChangePartKey: string | null
}>()

function isLatestChangePart(message: WebChatMessage, part: WebChatPart) {
  return messagePartKey(message, part) === props.latestChangePartKey
}

const emit = defineEmits<{
  copy: [message: WebChatMessage]
  regenerate: [message: WebChatMessage]
  edit: [message: WebChatMessage]
  cancelEdit: []
  saveEdit: [message: WebChatMessage]
  retryFailed: [message: WebChatMessage]
  editFailed: [message: WebChatMessage]
}>()

function setTooltipOpen(key: string, open: boolean) {
  if (open) {
    openTooltipKey.value = key
  } else if (openTooltipKey.value === key) {
    openTooltipKey.value = null
  }
}
</script>

<template>
  <template v-for="(group, index) in groupMessageParts(message.parts)" :key="`${message.id}-${group.type}-${index}`">
    <RunDetailsGroup
      v-if="group.type === 'process'"
      :parts="group.parts"
      :expanded-default="isRunning"
    />

    <template v-else>
      <div v-if="group.part.type === 'media' && group.part.attachments?.length" class="mb-2 flex flex-wrap gap-2">
        <ChatAttachmentPreview
          v-for="attachment in group.part.attachments"
          :key="attachment.id"
          :attachment="attachment"
        />
      </div>

      <ChatChangeSummary
        v-else-if="group.part.type === 'changes' && group.part.changes"
        :changes="group.part.changes"
        :initially-open="isLatestChangePart(message, group.part)"
      />

      <InteractivePromptCard
        v-else-if="group.part.type === 'interactive_prompt' && group.part.prompt"
        :prompt="group.part.prompt"
      />

      <div
        v-else-if="group.part.type === 'steer'"
        class="rounded-lg border border-dashed border-default bg-muted/30 px-3 py-2 text-sm text-muted"
      >
        <div class="mb-1 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-dimmed">
          <UIcon name="i-lucide-route" class="size-3.5" />
          <span>Steer</span>
        </div>
        <p class="whitespace-pre-wrap text-toned">
          {{ partText(group.part) }}
        </p>
      </div>

      <template v-else-if="group.part.type === 'text'">
        <Comark
          v-if="message.role === 'assistant'"
          :markdown="partText(group.part)"
          :plugins="[highlight()]"
          class="chat-message-markdown *:first:mt-0 *:last:mb-0"
        />
        <div v-else-if="editingMessageId === message.id" :ref="setEditingMessageContainer" class="w-full">
          <UChatPrompt
            v-model="editingText"
            :disabled="savingEditedMessageId === message.id"
            :rows="3"
            :autofocus="true"
            :autoresize="true"
            :ui="{ footer: 'justify-end' }"
            class="w-full min-w-72"
            @submit="emit('saveEdit', message)"
            @keydown.esc.prevent="emit('cancelEdit')"
          >
            <template #footer>
              <div class="flex w-full justify-end gap-2">
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
            </template>
          </UChatPrompt>
        </div>
        <p v-else class="whitespace-pre-wrap">
          {{ partText(group.part) }}
        </p>
      </template>
    </template>
  </template>

  <div
    v-if="message.role === 'user' && message.localStatus === 'failed'"
    class="mt-2 flex flex-wrap items-center justify-end gap-2 text-xs text-error"
  >
    <span>{{ message.localError || 'Not sent' }}</span>
    <UButton size="xs" color="error" variant="soft" label="Retry" @click="emit('retryFailed', message)" />
    <UButton size="xs" color="neutral" variant="ghost" label="Edit" @click="emit('editFailed', message)" />
  </div>

  <div
    :class="[
      'pointer-events-none absolute -bottom-6 flex w-max max-w-none flex-nowrap items-center gap-1 whitespace-nowrap text-xs leading-4 text-muted opacity-0 transition-opacity group-hover/message:pointer-events-auto group-hover/message:opacity-100 group-focus-within/message:pointer-events-auto group-focus-within/message:opacity-100',
      openTooltipKey ? 'pointer-events-auto opacity-100' : '',
      message.role === 'user' ? 'right-0 justify-end' : 'left-0 justify-start'
    ]"
  >
    <UTooltip
      v-if="message.role === 'assistant' && formatMessageTokenCount(message)"
      :content="tooltipContent"
      :ui="richTooltipUi"
      @update:open="setTooltipOpen('tokens', $event)"
    >
      <span class="cursor-default whitespace-nowrap">
        {{ formatMessageTokenCount(message) }}
      </span>
      <template #content>
        <div class="min-w-44 space-y-1 text-xs">
          <div
            v-for="row in messageTokenDetails(message)"
            :key="row.label"
            class="flex items-center justify-between gap-4"
          >
            <span class="text-muted">{{ row.label }}</span>
            <span class="font-medium text-highlighted">{{ row.value }}</span>
          </div>
          <p class="max-w-56 pt-1 text-[11px] leading-4 text-muted">
            {{ messageTokenTooltipNote(message) }}
          </p>
        </div>
      </template>
    </UTooltip>
    <span v-if="message.role === 'assistant' && formatMessageTokenCount(message)" aria-hidden="true">·</span>
    <UTooltip
      v-if="message.role === 'assistant' && formatMessageGenerationDuration(message)"
      :content="tooltipContent"
      :ui="richTooltipUi"
      @update:open="setTooltipOpen('duration', $event)"
    >
      <span class="cursor-default whitespace-nowrap">
        {{ formatMessageGenerationDuration(message) }}
      </span>
      <template #content>
        <div class="min-w-44 space-y-1 text-xs">
          <div
            v-for="row in messageDurationDetails(message)"
            :key="row.label"
            class="flex items-center justify-between gap-4"
          >
            <span class="text-muted">{{ row.label }}</span>
            <span class="font-medium text-highlighted">{{ row.value }}</span>
          </div>
          <p class="max-w-56 pt-1 text-[11px] leading-4 text-muted">
            Total is wall-clock from run start to completion; tool and waiting time are measured when events are available.
          </p>
        </div>
      </template>
    </UTooltip>
    <span v-if="message.role === 'assistant' && formatMessageGenerationDuration(message)" aria-hidden="true">·</span>
    <span class="cursor-default whitespace-nowrap" :title="messageTimestampTitle(message.createdAt)">
      {{ formatMessageTimestamp(message.createdAt) }}
    </span>
    <UTooltip
      v-if="message.role === 'user'"
      text="Edit prompt"
      :content="tooltipContent"
      @update:open="setTooltipOpen('edit', $event)"
    >
      <button
        type="button"
        class="inline-flex size-4 flex-none items-center justify-center text-muted hover:text-highlighted focus-visible:outline-2 focus-visible:outline-primary/50"
        aria-label="Edit message"
        :disabled="savingEditedMessageId === message.id || message.localStatus === 'failed'"
        @click="emit('edit', message)"
      >
        <UIcon name="i-lucide-pencil" class="size-3" />
      </button>
    </UTooltip>
    <UTooltip
      v-else
      text="Regenerate response"
      :content="tooltipContent"
      @update:open="setTooltipOpen('regenerate', $event)"
    >
      <button
        type="button"
        class="inline-flex size-4 flex-none items-center justify-center text-muted hover:text-highlighted focus-visible:outline-2 focus-visible:outline-primary/50 disabled:pointer-events-none disabled:opacity-50"
        aria-label="Regenerate response"
        :disabled="isRunning"
        @click="emit('regenerate', message)"
      >
        <UIcon name="i-lucide-rotate-ccw" class="size-3" />
      </button>
    </UTooltip>
    <UTooltip
      text="Copy"
      :content="tooltipContent"
      @update:open="setTooltipOpen('copy', $event)"
    >
      <button
        type="button"
        class="inline-flex size-4 flex-none items-center justify-center text-muted hover:text-highlighted focus-visible:outline-2 focus-visible:outline-primary/50"
        :aria-label="copiedMessageId === message.id ? 'Copied message' : 'Copy message'"
        @click="emit('copy', message)"
      >
        <UIcon :name="copiedMessageId === message.id ? 'i-lucide-check' : 'i-lucide-copy'" class="size-3" />
      </button>
    </UTooltip>
  </div>
</template>
