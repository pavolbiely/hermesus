<script setup lang="ts">
import type { ComponentPublicInstance, CSSProperties } from 'vue'
import type { PlanEntry } from '@agentclientprotocol/sdk'
import type { PermissionOption, RequestPermissionRequest } from '~/types/acp-api'
import type { AcpChatMessage } from '~/types/acp-chat'
import type { AcpChatMessageWithActions, MessageAction, MessageMetadataItem } from '~/composables/useAcpMessageActions'

type PendingPermission = {
  appRequestId: string
  request: RequestPermissionRequest
}

type ChatMessageProps = {
  side: 'left' | 'right'
  variant: 'soft' | 'naked'
  ui?: Record<string, string>
}

type ChatStatus = 'ready' | 'submitted' | 'streaming'

type Props = {
  messages: AcpChatMessage[]
  displayMessages: AcpChatMessageWithActions[]
  workspace: string | null
  loading: boolean
  error?: string | null
  scrollShadowStyle?: CSSProperties
  initialTranscriptScrollPending: boolean
  hasOlderMessages: boolean
  loadingOlderMessages: boolean
  pendingPermissions: PendingPermission[]
  planEntries: PlanEntry[]
  chatMessagesStatus: ChatStatus
  chatUserProps: ChatMessageProps
  chatAssistantProps: ChatMessageProps
  showRunActivityIndicator: boolean
  currentActivityLabel?: string | null
  currentActivityElapsedLabel?: string
  editingMessageId: string | null
  savingEditedMessageId: string | null
  submitting: boolean
  focusedAssistantMessageId: string | null
  setScrollContainer: (element: HTMLElement | null) => void
  setContentContainer: (element: HTMLElement | null) => void
  isActiveRunDetailMessage: (message: AcpChatMessage) => boolean
  shouldRenderRunDetailsBeforeMessage: (message: AcpChatMessage) => boolean
  shouldDefaultOpenThought: (message: AcpChatMessage, groupIndex: number) => boolean
  runDetailsSpacingClass: (message: AcpChatMessage, position: 'before' | 'after') => string
  hasRunDetails: (message: AcpChatMessage) => boolean
  hasAssistantFooter: (message: AcpChatMessage) => boolean
  isAssistantFooterVisible: (message: AcpChatMessage) => boolean
  messageMetadataItems: (message: AcpChatMessage) => MessageMetadataItem[]
  assistantMessageActions: (message: AcpChatMessage) => MessageAction[]
  isReadingAloud: (message: AcpChatMessage) => boolean
  isGeneratingAloud: (message: AcpChatMessage) => boolean
  readAloudStatusDetail: (message: AcpChatMessage) => string
  setRunDetailsElement: (messageId: string, element: Element | ComponentPublicInstance | null) => void
  onRunDetailsOpen: (open: boolean, messageId: string) => void
  setEditingMessageContainer: (element: Element | ComponentPublicInstance | null) => void
}

defineProps<Props>()
const editingText = defineModel<string>('editingText', { required: true })

const emit = defineEmits<{
  scroll: [event: Event]
  loadOlderMessages: []
  respondToPermission: [appRequestId: string, option?: PermissionOption]
  cancelEditing: []
  saveEdited: [message: AcpChatMessage]
  assistantHover: [messageId: string, hovered: boolean]
  assistantPointerLeave: [event: PointerEvent, messageId: string]
  assistantFocusIn: [messageId: string]
  assistantFocusOut: [event: FocusEvent, messageId: string]
}>()

function permissionTitle(permission: PendingPermission) {
  const toolCall = permission.request.toolCall as Record<string, unknown>
  const value = toolCall.title ?? toolCall.name ?? toolCall.kind ?? toolCall.toolCallId
  return typeof value === 'string' && value ? value : 'Permission required'
}
</script>

<template>
  <div
    :ref="element => setScrollContainer(element as HTMLElement | null)"
    class="min-h-0 flex-1 overflow-y-auto px-4 py-6"
    :style="scrollShadowStyle"
    @scroll.passive="emit('scroll', $event)"
  >
    <div
      :ref="element => setContentContainer(element as HTMLElement | null)"
      class="mx-auto w-full max-w-3xl space-y-4"
      :class="initialTranscriptScrollPending && messages.length ? 'invisible' : ''"
    >
      <UAlert
        v-if="error"
        color="error"
        variant="soft"
        title="ACP chat error"
        :description="error"
      />

      <div v-if="loading && !messages.length" class="space-y-4" aria-label="Loading ACP session">
        <USkeleton class="h-16 w-4/5 rounded-2xl" />
        <USkeleton class="ml-auto h-10 w-2/5 rounded-2xl" />
      </div>

      <div v-if="hasOlderMessages" class="flex justify-center">
        <UButton
          size="sm"
          color="neutral"
          variant="ghost"
          icon="i-lucide-arrow-up"
          :loading="loadingOlderMessages"
          @click="emit('loadOlderMessages')"
        >
          Load older messages
        </UButton>
      </div>

      <UCard
        v-for="permission in pendingPermissions"
        :key="permission.appRequestId"
        variant="soft"
        :ui="{ body: 'space-y-3' }"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <p class="text-sm font-medium text-highlighted">{{ permissionTitle(permission) }}</p>
            <p class="text-xs text-muted">Hermes is requesting permission before running this tool.</p>
          </div>
          <UBadge color="warning" variant="soft" size="sm">Permission</UBadge>
        </div>
        <div class="flex flex-wrap gap-2">
          <UButton
            v-for="option in permission.request.options"
            :key="option.optionId"
            size="sm"
            :color="option.kind.startsWith('allow') ? 'primary' : 'neutral'"
            :variant="option.kind.startsWith('allow') ? 'solid' : 'soft'"
            @click="emit('respondToPermission', permission.appRequestId, option)"
          >
            {{ option.name }}
          </UButton>
          <UButton
            size="sm"
            color="neutral"
            variant="ghost"
            @click="emit('respondToPermission', permission.appRequestId)"
          >
            Cancel
          </UButton>
        </div>
      </UCard>

      <AcpPlanCard
        v-if="planEntries.length"
        :entries="planEntries"
      />

      <UChatMessages
        v-if="!loading || messages.length"
        :messages="displayMessages"
        :status="chatMessagesStatus"
        :should-auto-scroll="false"
        :should-scroll-to-bottom="true"
        :auto-scroll="true"
        auto-scroll-icon="i-lucide-arrow-down"
        :user="chatUserProps"
        :assistant="chatAssistantProps"
      >
        <template #content="{ message }: { message: AcpChatMessageWithActions }">
          <AcpChatMessageContent
            :message="message"
            :workspace="workspace"
            v-model:editing-text="editingText"
            :editing-message-id="editingMessageId"
            :saving-edited-message-id="savingEditedMessageId"
            :submitting="submitting"
            :focused-assistant-message-id="focusedAssistantMessageId"
            :is-active-run-detail-message="isActiveRunDetailMessage"
            :should-render-run-details-before-message="shouldRenderRunDetailsBeforeMessage"
            :should-default-open-thought="shouldDefaultOpenThought"
            :run-details-spacing-class="runDetailsSpacingClass"
            :has-run-details="hasRunDetails"
            :has-assistant-footer="hasAssistantFooter"
            :is-assistant-footer-visible="isAssistantFooterVisible"
            :message-metadata-items="messageMetadataItems"
            :assistant-message-actions="assistantMessageActions"
            :is-reading-aloud="isReadingAloud"
            :is-generating-aloud="isGeneratingAloud"
            :read-aloud-status-detail="readAloudStatusDetail"
            :set-run-details-element="setRunDetailsElement"
            :on-run-details-open="onRunDetailsOpen"
            :set-editing-message-container="setEditingMessageContainer"
            @cancel-editing="emit('cancelEditing')"
            @save-edited="emit('saveEdited', $event)"
            @assistant-hover="(messageId, hovered) => emit('assistantHover', messageId, hovered)"
            @assistant-pointer-leave="emit('assistantPointerLeave', $event, message.id)"
            @assistant-focus-in="emit('assistantFocusIn', $event)"
            @assistant-focus-out="emit('assistantFocusOut', $event, message.id)"
          />
        </template>
        <template #actions="{ message }: { message: AcpChatMessageWithActions }">
          <div
            v-if="message.role === 'user' && editingMessageId !== message.id && (messageMetadataItems(message).length || message.actions?.length)"
            class="flex min-h-4 flex-nowrap items-center justify-end gap-x-1.5 whitespace-nowrap text-xs leading-none text-muted"
          >
            <template
              v-for="(item, itemIndex) in messageMetadataItems(message)"
              :key="item.key"
            >
              <span v-if="itemIndex" class="text-dimmed">·</span>
              <span :title="item.title">{{ item.label }}</span>
            </template>
            <span
              v-if="messageMetadataItems(message).length && message.actions?.length"
              class="text-dimmed"
            >·</span>
            <UTooltip
              v-for="(action, actionIndex) in message.actions"
              :key="actionIndex"
              :text="action.label"
            >
              <UButton
                size="xs"
                :icon="action.icon"
                :color="action.color || 'neutral'"
                variant="ghost"
                :disabled="action.disabled"
                :aria-label="action.label"
                class="-my-0.5 size-4 p-0 text-muted hover:text-toned disabled:text-dimmed"
                :ui="{ leadingIcon: 'size-3' }"
                @click="action.onClick($event, message)"
              />
            </UTooltip>
          </div>
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
          <AcpRunActivityIndicator
            :label="currentActivityLabel || 'Working…'"
            :elapsed-label="currentActivityElapsedLabel"
          />
        </template>
      </UChatMessage>
    </div>
  </div>
</template>
