<script setup lang="ts">
import type {
  AcpListSessionsResponse,
} from '~/types/acp-api'
import type { AcpChatMessage } from '~/types/acp-chat'
import { useScrollShadow } from '@nuxt/ui/composables'
import { acpMessageText } from '~/utils/acpMessageMetadata'
import { runDetailGroups } from '~/utils/acpRunDetails'
import { attachmentsAsFileParts, groupProcessMessages } from '~/utils/acpChatMessageDisplay'
import {
  hasRunDetails,
  runActivityLabel,
  runActivityTitle,
  runDetailsSpacingClass as runDetailsSpacingClassForMessage,
  shouldRenderRunDetailsBeforeMessage as shouldRenderRunDetailsBeforeMessageForTurn
} from '~/utils/acpRunDetailDisplay'
import { chatSessionDraftId } from '~/utils/chatDrafts'
import { acpSidebarSessions } from '~/utils/acpSidebarSessions'
import { shouldAutoSendQueuedMessage } from '~/utils/queuedMessages'

const route = useRoute()
const router = useRouter()
const api = useAcpApi()
const sidebarSessionsData = useNuxtData<AcpListSessionsResponse>('acp-sidebar-sessions')
const context = useChatComposerContext()
const pendingAcpPrompts = usePendingAcpPrompt()
const activeAcpPrompts = useAcpActivePrompts()
const transcript = useAcpTranscript()
const queuedMessages = useQueuedMessages()
const readAloud = useAcpMessageReadAloud()
const toast = useToast()

const sessionId = computed(() => String(route.params.id || ''))
const draftId = computed(() => chatSessionDraftId(sessionId.value))
const { input, clearDraft } = useChatDraft(draftId)
const messagesScrollContainer = ref<HTMLElement | null>(null)
const messagesContentContainer = ref<HTMLElement | null>(null)
const composer = ref<{ focus: () => void } | null>(null)
function setMessagesScrollContainer(element: HTMLElement | null) {
  messagesScrollContainer.value = element
}

function setMessagesContentContainer(element: HTMLElement | null) {
  messagesContentContainer.value = element
}

const { style: messagesScrollShadowStyle } = useScrollShadow(messagesScrollContainer)
let latestSubmitScrollSequence = 0

const { setRunDetailsElement, onRunDetailsOpen } = useAcpRunDetailsScroll({
  scrollContainer: messagesScrollContainer
})
const queuedForSession = computed(() => queuedMessages.forSession(sessionId.value))
const messages = computed(() => transcript.messages.value)
const groupedMessages = computed(() => groupProcessMessages(messages.value))
const {
  activePromptTurnId,
  submitStatusState,
  submitting,
  submitStatus,
  chatMessagesStatus,
  currentActivityLabel,
  currentActivityTitle,
  showRunActivityIndicator,
  currentActivityElapsedLabel,
  promoteSubmittedStatusToStreaming,
  stopActivePromptClock
} = useAcpActiveRunStatus({
  sessionId,
  messages,
  displayMessages: groupedMessages,
  activePrompts: activeAcpPrompts,
  hasRunDetails,
  getRunActivityLabel: runActivityLabel,
  getRunActivityTitle: runActivityTitle
})
const chatBottomFollow = useChatBottomFollow({
  scrollContainer: messagesScrollContainer,
  contentContainer: messagesContentContainer,
  active: submitting,
  waitForFrame: waitForAnimationFrame
})
const currentAcpSession = computed(() => sidebarSessionsData.data.value?.sessions.find(session => session.sessionId === sessionId.value) || null)
const currentSidebarSession = computed(() => acpSidebarSessions(sidebarSessionsData.data.value).find(session => session.id === sessionId.value) || null)
watch([currentSidebarSession, context.workspaces], ([session]) => {
  if (!sidebarSessionsData.data.value) return
  context.selectWorkspace(session?.workspace || null)
}, { immediate: true })
const inferredChatTitle = computed(() => {
  const firstUserMessage = messages.value.find(message => message.role === 'user')
  const text = firstUserMessage ? acpMessageText(firstUserMessage).trim().replace(/\s+/g, ' ') : ''
  return text.length > 80 ? `${text.slice(0, 77)}…` : text
})
const chatHeaderTitle = computed(() => {
  const currentAcp = currentAcpSession.value
  const acpTitle = currentAcp?.appMetadata?.title?.trim()
    || currentAcp?.appLineage?.rootTitle?.trim()
    || currentAcp?.title?.trim()
  if (acpTitle) return acpTitle

  const currentSession = currentSidebarSession.value
  const title = currentSession?.title?.trim()
  if (title) return title

  const preview = currentSession?.preview?.trim()
  if (preview && preview !== 'ACP chat') return preview

  if (inferredChatTitle.value) return inferredChatTitle.value
  return loading.value ? 'Loading chat…' : 'Untitled chat'
})
const chatUserProps = {
  side: 'right' as const,
  variant: 'soft' as const,
  ui: {
    container: 'pb-6',
    actions: 'right-0 bottom-0 w-max'
  }
}
const chatAssistantProps = {
  side: 'left' as const,
  variant: 'naked' as const
}
const {
  modelState,
  modeState,
  configOptions,
  availableCommands,
  updatingSessionConfig,
  selectedModelId,
  modelItems,
  reasoningItems,
  workspaceItems,
  workspaceLabel,
  selectedModelLabel,
  selectedReasoningId,
  selectedModeLabel,
  slashCommandItems,
  updateSessionMode,
  updateSessionModel
} = useAcpSessionConfigControls({
  sessionId,
  workspaces: context.workspaces,
  selectedWorkspace: context.selectedWorkspace,
  api,
  showError
})

const {
  loading,
  initialTranscriptScrollPending,
  pendingPermissions,
  planEntries,
  loadingOlderMessages,
  hasOlderMessages,
  error,
  initializeSession,
  abortActiveSessionLoad,
  closeSessionEvents,
  loadOlderMessages,
  respondToPermission
} = useAcpSessionPage({
  sessionId,
  messagesScrollContainer,
  pendingPrompts: pendingAcpPrompts,
  queryPrompt: computed(() => typeof route.query.prompt === 'string' ? route.query.prompt : ''),
  replaceRouteQuery: () => router.replace({ path: route.path, query: {} }),
  loadSession: api.loadSession,
  subscribeSession: api.subscribeSession,
  respondToPermissionRequest: api.respondToPermission,
  transcript,
  modelState,
  modeState,
  configOptions,
  availableCommands,
  activePromptTurnId,
  submitStatusState,
  activePrompts: activeAcpPrompts,
  onPromptRequested: (message, attachments) => sendPrompt(message, attachments),
  onSessionTouched: sessionId => touchSidebarSession(sessionId),
  showError,
  waitForFrame: waitForAnimationFrame
})

const {
  steeringQueuedMessageId,
  queuedMessageToSendAfterStop,
  autoSendingQueuedMessage,
  onSubmit,
  editQueuedMessage,
  deleteQueuedMessage,
  steerQueuedMessage,
  sendNextQueuedMessage,
  sendPrompt,
  stopPrompt,
  touchSidebarSession
} = useAcpPromptController({
  sessionId,
  input,
  loading,
  error,
  pendingPermissions,
  planEntries,
  modelState,
  modeState,
  configOptions,
  availableCommands,
  activePromptTurnId,
  submitStatusState,
  submitting,
  submitStatus,
  sidebarSessionsData,
  context,
  api,
  transcript,
  queuedMessages,
  queuedForSession,
  activePrompts: activeAcpPrompts,
  clearDraft,
  focusComposer: () => composer.value?.focus(),
  scrollSubmittedMessageToBottom,
  promoteSubmittedStatusToStreaming,
  showError,
  toast
})
const {
  editingMessageId,
  editingText,
  savingEditedMessageId,
  setEditingMessageContainer,
  cancelEditingUserMessage,
  startEditingUserMessage,
  saveEditedUserMessage
} = useAcpMessageEditing({
  submitting,
  sendPrompt
})
const {
  focusedAssistantMessageId,
  withNativeMessageActions,
  assistantMessageActions,
  isReadingAloud,
  isGeneratingAloud,
  readAloudStatusDetail,
  setAssistantMessageHover,
  onAssistantMessagePointerLeave,
  onAssistantMessageFocusOut,
  isAssistantFooterVisible,
  hasAssistantFooter,
  messageMetadataItems
} = useAcpMessageActions({
  messages,
  activePromptTurnId,
  submitting,
  editingMessageId,
  readAloud,
  toast,
  showError,
  sendPrompt,
  startEditingUserMessage
})
const displayMessages = computed(() => groupedMessages.value.map(message => attachmentsAsFileParts(withNativeMessageActions(message))))
const canAutoSendQueuedMessage = computed(() => shouldAutoSendQueuedMessage({
  hasSession: Boolean(sessionId.value && !loading.value),
  queuedCount: queuedForSession.value.length + (queuedMessageToSendAfterStop.value ? 1 : 0),
  isRunning: submitting.value,
  hasActiveRun: Boolean(activePromptTurnId.value),
  isSubmitting: submitStatus.value === 'submitted' || autoSendingQueuedMessage.value
}))
onMounted(async () => {
  await Promise.all([context.initialize(), initializeSession()])
})

onBeforeUnmount(() => {
  abortActiveSessionLoad()
  closeSessionEvents()
  stopActivePromptClock()
})

watch(sessionId, (newSessionId) => {
  void initializeSession(newSessionId)
})


watch(canAutoSendQueuedMessage, (shouldSend) => {
  if (shouldSend) void sendNextQueuedMessage()
}, { immediate: true })


function waitForAnimationFrame() {
  return new Promise<void>((resolve) => {
    requestAnimationFrame(() => resolve())
  })
}

function scrollSubmittedMessageToBottom(turnId: string) {
  if (!import.meta.client) return

  const scrollSequence = ++latestSubmitScrollSequence
  const isCurrentSubmit = () => (
    scrollSequence === latestSubmitScrollSequence
    && activePromptTurnId.value === turnId
    && Boolean(sessionId.value)
  )

  void chatBottomFollow.scrollToBottomAfterRender({
    isCurrent: isCurrentSubmit,
    stableFrameCount: 2,
    maxFrameCount: 8
  })
}

function showError(err: unknown, fallback: string) {
  const message = err instanceof Error ? err.message : String(err || fallback)
  error.value = message
  toast.add({ color: 'error', title: fallback, description: message })
}

function isActiveRunDetailMessage(message: AcpChatMessage) {
  return Boolean(activePromptTurnId.value && message.turnId === activePromptTurnId.value)
}

function shouldRenderRunDetailsBeforeMessage(message: AcpChatMessage) {
  return shouldRenderRunDetailsBeforeMessageForTurn(message, activePromptTurnId.value)
}

function shouldDefaultOpenThought(message: AcpChatMessage, groupIndex: number) {
  return isActiveRunDetailMessage(message) && groupIndex === runDetailGroups(message).length - 1
}

function runDetailsSpacingClass(message: AcpChatMessage, position: 'before' | 'after') {
  return runDetailsSpacingClassForMessage(message, position, hasAssistantFooter(message))
}

function appendVoiceText(text: string) {
  input.value = input.value ? `${input.value.trimEnd()} ${text}` : text
}

function showVoiceError(message: string) {
  toast.add({ color: 'error', title: 'Voice input failed', description: message })
}

async function attachFiles(files: File[]) {
  try {
    await context.uploadFiles(files)
  } catch (err) {
    showError(err, 'Failed to attach files')
  }
}

</script>

<template>
  <UDashboardPanel>
    <template #header>
      <AppNavbar :title="chatHeaderTitle" />
    </template>

    <template #body>
      <div class="flex h-full min-h-0 flex-col">
        <AcpChatTranscript
          v-model:editing-text="editingText"
          :messages="messages"
          :display-messages="displayMessages"
          :workspace="context.selectedWorkspace.value"
          :loading="loading"
          :error="error"
          :scroll-shadow-style="messagesScrollShadowStyle"
          :initial-transcript-scroll-pending="initialTranscriptScrollPending"
          :has-older-messages="hasOlderMessages"
          :loading-older-messages="loadingOlderMessages"
          :pending-permissions="pendingPermissions"
          :plan-entries="planEntries"
          :chat-messages-status="chatMessagesStatus"
          :chat-user-props="chatUserProps"
          :chat-assistant-props="chatAssistantProps"
          :show-run-activity-indicator="showRunActivityIndicator"
          :current-activity-label="currentActivityLabel"
          :current-activity-title="currentActivityTitle"
          :current-activity-elapsed-label="currentActivityElapsedLabel"
          :editing-message-id="editingMessageId"
          :saving-edited-message-id="savingEditedMessageId"
          :submitting="submitting"
          :focused-assistant-message-id="focusedAssistantMessageId"
          :set-scroll-container="setMessagesScrollContainer"
          :set-content-container="setMessagesContentContainer"
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
          @scroll="chatBottomFollow.onScroll"
          @load-older-messages="loadOlderMessages"
          @respond-to-permission="respondToPermission"
          @cancel-editing="cancelEditingUserMessage"
          @save-edited="saveEditedUserMessage"
          @assistant-hover="setAssistantMessageHover"
          @assistant-pointer-leave="onAssistantMessagePointerLeave"
          @assistant-focus-in="focusedAssistantMessageId = $event"
          @assistant-focus-out="onAssistantMessageFocusOut"
        />

        <div class="shrink-0 bg-default/80 px-4 py-4 backdrop-blur">
          <div class="mx-auto w-full max-w-3xl">
            <AcpChatComposer
              ref="composer"
              v-model="input"
              :commands="slashCommandItems"
              :queued-messages="queuedForSession"
              :steering-id="steeringQueuedMessageId"
              :loading="loading"
              :submit-status="submitStatus"
              :submit-disabled="(!input.trim() && !context.attachments.value.length && !submitting)"
              :attachments="context.attachments.value"
              :attachments-loading="context.attachmentsLoading.value"
              :workspaces="workspaceItems"
              :selected-workspace="context.selectedWorkspace.value"
              :workspaces-loading="context.workspacesLoading.value"
              :workspace-label="workspaceLabel"
              :models="modelItems"
              :selected-model="selectedModelId"
              :model-label="selectedModelLabel || 'Model'"
              :modes="reasoningItems"
              :selected-mode="selectedReasoningId"
              :reasoning-label="selectedModeLabel || 'Reasoning'"
              :updating-session-config="updatingSessionConfig"
              @submit="onSubmit"
              @edit-queued="editQueuedMessage"
              @delete-queued="deleteQueuedMessage"
              @steer-queued="steerQueuedMessage"
              @stop="stopPrompt"
              @attach-files="attachFiles"
              @remove-attachment="context.removeAttachment"
              @voice-text="appendVoiceText"
              @voice-error="showVoiceError"
              @update-selected-workspace="context.selectWorkspace"
              @update-selected-model="updateSessionModel"
              @update-selected-mode="updateSessionMode"
            />
          </div>
        </div>
      </div>
    </template>
  </UDashboardPanel>
</template>
