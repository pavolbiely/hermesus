<script setup lang="ts">
import type { WebChatMessage } from '~/types/web-chat'

const props = defineProps<{
  isLoadingSession: boolean
  loadingSkeletonCount: number
  sessionError: unknown
  hasSession: boolean
  hasOlderMessages: boolean
  olderMessagesError: string | null
  olderMessagesLabel: string
  loadingOlderMessages: boolean
  messages: WebChatMessage[]
  chatMessagesStatus: 'ready' | 'submitted' | 'streaming' | 'error'
  currentActivityLabel: string | null
  showRunActivityIndicator: boolean
  promptOverlayHeight: number
  sessionId: string
  copiedMessageId: string | null
  editingMessageId: string | null
  editingText: string
  savingEditedMessageId: string | null
  isRunning: boolean
  activeRunAssistantMessageId: string | null
  workspace: string | null
  latestChangePartKey: string | null
  setEditingMessageContainer: (el: unknown) => void
}>()

const emit = defineEmits<{
  retryLoad: []
  loadOlderMessages: []
  copy: [message: WebChatMessage]
  regenerate: [message: WebChatMessage]
  edit: [message: WebChatMessage]
  cancelEdit: []
  saveEdit: [message: WebChatMessage]
  retryFailed: [message: WebChatMessage]
  editFailed: [message: WebChatMessage]
  'update:chatContainer': [element: HTMLElement | null]
  'update:olderMessagesSentinel': [element: HTMLElement | null]
  'update:bottomReadSentinel': [element: HTMLElement | null]
  'update:editingText': [text: string]
}>()

function setElement(event: 'update:chatContainer' | 'update:olderMessagesSentinel' | 'update:bottomReadSentinel', element: Element | null) {
  const htmlElement = element instanceof HTMLElement ? element : null
  if (event === 'update:chatContainer') emit('update:chatContainer', htmlElement)
  else if (event === 'update:olderMessagesSentinel') emit('update:olderMessagesSentinel', htmlElement)
  else emit('update:bottomReadSentinel', htmlElement)
}
</script>

<template>
  <div :ref="element => setElement('update:chatContainer', element as Element | null)">
    <div v-if="isLoadingSession" class="min-h-[calc(100dvh-14rem)] space-y-6 pt-2" aria-label="Loading chat">
      <div
        v-for="index in loadingSkeletonCount"
        :key="index"
        class="flex animate-pulse"
        :class="index % 2 === 0 ? 'justify-end' : 'justify-start'"
      >
        <USkeleton
          class="rounded-2xl"
          :class="[
            index % 2 === 0 ? 'h-10 w-3/5' : 'h-20 w-4/5',
            index === loadingSkeletonCount ? 'opacity-45' : 'opacity-70'
          ]"
        />
      </div>
    </div>

    <div v-else-if="sessionError || !hasSession" class="flex min-h-[40vh] items-center justify-center text-center">
      <div class="max-w-sm space-y-3">
        <UIcon name="i-lucide-message-circle-warning" class="mx-auto size-8 text-muted" />
        <div class="space-y-1">
          <h2 class="font-medium text-highlighted">Could not load chat</h2>
          <p class="text-sm text-muted">The chat may have been deleted or the backend is unavailable.</p>
        </div>
        <UButton color="neutral" variant="soft" label="Try again" @click="emit('retryLoad')" />
      </div>
    </div>

    <template v-else>
      <div
        v-if="hasOlderMessages || olderMessagesError"
        :ref="element => setElement('update:olderMessagesSentinel', element as Element | null)"
        class="mb-4 flex flex-col items-center gap-2"
      >
        <UButton
          v-if="hasOlderMessages"
          color="neutral"
          variant="ghost"
          size="sm"
          :label="olderMessagesLabel"
          :loading="loadingOlderMessages"
          :disabled="loadingOlderMessages"
          @click="emit('loadOlderMessages')"
        />
        <p v-if="olderMessagesError" class="text-xs text-error">
          {{ olderMessagesError }}
        </p>
      </div>

      <UChatMessages
        :messages="messages"
        :status="chatMessagesStatus"
        :shouldAutoScroll="false"
        :shouldScrollToBottom="true"
        :autoScroll="true"
        :ui="{
          viewport: 'fixed top-auto bottom-[var(--chat-auto-scroll-bottom,128px)] left-[var(--chat-auto-scroll-left,0px)] w-[var(--chat-auto-scroll-width,100vw)] z-50 flex justify-center pointer-events-none',
          autoScroll: 'pointer-events-auto rounded-full shadow-sm'
        }"
        class="[--last-message-height:0px]"
      >
        <template #indicator>
          <ChatRunActivityIndicator :label="currentActivityLabel || 'Working…'" />
        </template>

        <template #content="{ message }: { message: WebChatMessage }">
          <ChatMessageContent
            :editing-text="props.editingText"
            :message="message"
            :session-id="sessionId"
            :copied-message-id="copiedMessageId"
            :editing-message-id="editingMessageId"
            :saving-edited-message-id="savingEditedMessageId"
            :is-running="isRunning"
            :is-active-run-message="message.id === activeRunAssistantMessageId"
            :workspace="workspace"
            :latest-change-part-key="latestChangePartKey"
            :set-editing-message-container="setEditingMessageContainer"
            @update:editing-text="emit('update:editingText', $event)"
            @copy="emit('copy', $event)"
            @regenerate="emit('regenerate', $event)"
            @edit="emit('edit', $event)"
            @cancel-edit="emit('cancelEdit')"
            @save-edit="emit('saveEdit', $event)"
            @retry-failed="emit('retryFailed', $event)"
            @edit-failed="emit('editFailed', $event)"
          />
        </template>
      </UChatMessages>

      <UChatMessage
        v-if="showRunActivityIndicator"
        id="run-activity-indicator"
        role="assistant"
        variant="naked"
        :parts="[]"
        class="px-2.5"
      >
        <template #content>
          <ChatRunActivityIndicator :label="currentActivityLabel || 'Working…'" />
        </template>
      </UChatMessage>

      <div
        v-if="promptOverlayHeight"
        :style="{ height: `${promptOverlayHeight + 12}px` }"
        aria-hidden="true"
      />
      <div
        :ref="element => setElement('update:bottomReadSentinel', element as Element | null)"
        class="h-px w-full"
        aria-hidden="true"
      />
    </template>
  </div>
</template>
