<script setup lang="ts">
import type { ComponentPublicInstance } from 'vue'
import type { AcpChatMessage } from '~/types/acp-chat'
import type { AcpChatMessageWithActions, MessageAction, MessageMetadataItem } from '~/composables/useAcpMessageActions'
import { partText, systemEventSeverity, systemEventTitle } from '~/utils/acpChatMessageDisplay'
import { runDetailSummary } from '~/utils/acpRunDetailDisplay'
import { runDetailGroups, toolParts } from '~/utils/acpRunDetails'

const props = defineProps<{
  message: AcpChatMessageWithActions
  workspace: string | null
  editingMessageId: string | null
  editingText: string
  savingEditedMessageId: string | null
  submitting: boolean
  focusedAssistantMessageId: string | null
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
}>()

const emit = defineEmits<{
  'update:editingText': [value: string]
  cancelEditing: []
  saveEdited: [message: AcpChatMessage]
  assistantHover: [messageId: string, hovered: boolean]
  assistantPointerLeave: [event: PointerEvent, messageId: string]
  assistantFocusIn: [messageId: string]
  assistantFocusOut: [event: FocusEvent, messageId: string]
}>()

const editingTextModel = computed({
  get: () => props.editingText,
  set: value => emit('update:editingText', value)
})

function runDetailsIcon(message: AcpChatMessage) {
  return toolParts(message).some(part => part.error) ? 'i-lucide-circle-alert' : 'i-lucide-list-tree'
}

function runDetailsLeadingIconClass(message: AcpChatMessage) {
  return toolParts(message).some(part => part.error) ? 'text-error' : 'text-dimmed'
}
</script>

<template>
  <template v-if="message.role === 'user'">
    <div
      v-if="editingMessageId === message.id"
      :ref="element => setEditingMessageContainer(element)"
      class="min-w-[min(28rem,calc(100vw-4rem))] space-y-2"
    >
      <UTextarea
        v-model="editingTextModel"
        :maxrows="10"
        autofocus
        autoresize
        class="w-full"
        :disabled="submitting || savingEditedMessageId === message.id"
        @keydown.esc.prevent="emit('cancelEditing')"
        @keydown.meta.enter.prevent="emit('saveEdited', message)"
        @keydown.ctrl.enter.prevent="emit('saveEdited', message)"
      />
      <div class="flex justify-end gap-2">
        <UButton
          size="xs"
          color="neutral"
          variant="ghost"
          label="Cancel"
          :disabled="savingEditedMessageId === message.id"
          @click="emit('cancelEditing')"
        />
        <UButton
          size="xs"
          color="primary"
          label="Send edited"
          :loading="savingEditedMessageId === message.id"
          :disabled="!editingTextModel.trim() || submitting"
          @click="emit('saveEdited', message)"
        />
      </div>
    </div>
    <template v-else>
      {{ partText(message) }}
    </template>
  </template>

  <div
    v-else-if="message.role === 'system'"
    class="rounded-lg border border-dashed bg-muted/30 px-3 py-2 text-sm text-muted"
    :class="{
      'border-error/30': systemEventSeverity(message) === 'error',
      'border-warning/30': systemEventSeverity(message) === 'warning',
      'border-default': systemEventSeverity(message) !== 'error' && systemEventSeverity(message) !== 'warning'
    }"
  >
    <div class="mb-1 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-dimmed">
      <UIcon name="i-lucide-route" class="size-3.5" />
      <span>{{ systemEventTitle(message) }}</span>
    </div>
    <p v-if="partText(message)" class="whitespace-pre-wrap text-toned">
      {{ partText(message) }}
    </p>
  </div>

  <div
    v-else
    class="inline-block max-w-full"
    @pointerenter="emit('assistantHover', message.id, true)"
    @pointerleave="event => emit('assistantPointerLeave', event, message.id)"
    @focusin="emit('assistantFocusIn', message.id)"
    @focusout="event => emit('assistantFocusOut', event, message.id)"
  >
    <UChatTool
      v-if="shouldRenderRunDetailsBeforeMessage(message)"
      text="Run details"
      :suffix="runDetailSummary(message)"
      :icon="runDetailsIcon(message)"
      variant="card"
      chevron="trailing"
      :default-open="isActiveRunDetailMessage(message)"
      :ref="element => setRunDetailsElement(message.id, element)"
      :class="runDetailsSpacingClass(message, 'before')"
      :ui="{
        root: 'bg-muted/20',
        trigger: 'px-3 py-2',
        leadingIcon: runDetailsLeadingIconClass(message),
        body: 'max-h-none space-y-2 overflow-visible border-t border-default p-3 text-sm text-dimmed whitespace-normal'
      }"
      @update:open="open => onRunDetailsOpen(open, message.id)"
    >
      <div
        v-for="(group, groupIndex) in runDetailGroups(message)"
        :key="group.id"
        class="space-y-2"
        :class="groupIndex ? 'border-t border-default/70 pt-2' : ''"
      >
        <AcpThoughtItem
          v-if="group.thoughtText || group.thoughtDetail"
          :text="group.thoughtText"
          :detail="group.thoughtDetail"
          :default-open="shouldDefaultOpenThought(message, groupIndex)"
        />

        <AcpToolCallItem
          v-for="part in group.tools"
          :key="part.toolCallId"
          :part="part"
        />
      </div>
    </UChatTool>

    <AcpMessageMarkdown
      v-if="partText(message)"
      :markdown="partText(message)"
      :workspace="workspace"
      :streaming="isActiveRunDetailMessage(message)"
    />

    <div
      v-if="hasAssistantFooter(message)"
      class="mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs leading-none text-muted transition-opacity"
      :class="isAssistantFooterVisible(message) ? 'opacity-100' : 'opacity-0'"
    >
      <template
        v-for="(item, itemIndex) in messageMetadataItems(message)"
        :key="item.key"
      >
        <span v-if="itemIndex" class="text-dimmed">·</span>
        <span :title="item.title">{{ item.label }}</span>
      </template>
      <span
        v-if="assistantMessageActions(message).length"
        class="inline-flex items-center gap-x-1.5"
      >
        <span
          v-if="messageMetadataItems(message).length"
          class="text-dimmed"
        >·</span>
        <UTooltip
          v-for="(action, actionIndex) in assistantMessageActions(message)"
          :key="actionIndex"
          :text="action.label"
        >
          <button
            v-if="action.kind === 'read-aloud'"
            type="button"
            class="inline-flex size-4 flex-none items-center justify-center text-muted hover:text-highlighted focus-visible:outline-2 focus-visible:outline-primary/50 disabled:pointer-events-none disabled:opacity-50"
            :class="isReadingAloud(message) || isGeneratingAloud(message) ? 'text-primary hover:text-primary' : ''"
            :disabled="action.disabled"
            :aria-label="action.label"
            @click.stop.prevent="action.onClick($event, message)"
          >
            <UIcon
              :name="action.icon"
              class="size-3"
              :class="isGeneratingAloud(message) ? 'animate-spin' : ''"
            />
          </button>
          <UButton
            v-else
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
        <span v-if="readAloudStatusDetail(message)" aria-hidden="true">·</span>
        <em
          v-if="readAloudStatusDetail(message)"
          class="cursor-default whitespace-nowrap text-muted"
        >
          {{ readAloudStatusDetail(message) }}
        </em>
      </span>
    </div>

    <UChatTool
      v-if="hasRunDetails(message) && !shouldRenderRunDetailsBeforeMessage(message)"
      text="Run details"
      :suffix="runDetailSummary(message)"
      :icon="runDetailsIcon(message)"
      variant="card"
      chevron="trailing"
      :default-open="isActiveRunDetailMessage(message)"
      :ref="element => setRunDetailsElement(message.id, element)"
      :class="runDetailsSpacingClass(message, 'after')"
      :ui="{
        root: 'bg-muted/20',
        trigger: 'px-3 py-2',
        leadingIcon: runDetailsLeadingIconClass(message),
        body: 'max-h-none space-y-2 overflow-visible border-t border-default p-3 text-sm text-dimmed whitespace-normal'
      }"
      @update:open="open => onRunDetailsOpen(open, message.id)"
    >
      <div
        v-for="(group, groupIndex) in runDetailGroups(message)"
        :key="group.id"
        class="space-y-2"
        :class="groupIndex ? 'border-t border-default/70 pt-2' : ''"
      >
        <AcpThoughtItem
          v-if="group.thoughtText || group.thoughtDetail"
          :text="group.thoughtText"
          :detail="group.thoughtDetail"
          :default-open="shouldDefaultOpenThought(message, groupIndex)"
        />

        <AcpToolCallItem
          v-for="part in group.tools"
          :key="part.toolCallId"
          :part="part"
        />
      </div>
    </UChatTool>
  </div>
</template>
