<script setup lang="ts">
import { prepareNotificationSound } from '../../utils/notificationSound'
import { recoverActiveRun } from '../../utils/activeRunRecovery'
import { connectRouteRun } from '../../utils/routeRunConnection'
import type { WebChatMessage } from '~/types/web-chat'
import type { QueuedMessage } from '~/utils/queuedMessages'
import { messageText } from '~/utils/chatMessages'
import { writeClipboardText } from '~/utils/clipboard'

const route = useRoute()
const api = useHermesApi()
const composer = useChatComposerCapabilities()
const activeChatRuns = useActiveChatRuns()
const context = useChatComposerContext()
const toast = useToast()
const input = ref('')
const slashCommands = useSlashCommands({ input })
const copiedMessageId = ref<string | null>(null)
const workspaceInvalidSignal = ref(0)
let copiedMessageTimer: ReturnType<typeof setTimeout> | undefined
const refreshSessions = inject<() => Promise<void> | void>('refreshSessions')

const sessionId = computed(() => String(route.params.id))
const queuedMessages = useQueuedMessages()
const queuedForSession = computed(() => queuedMessages.forSession(sessionId.value))
const steeringQueuedMessageId = ref<string | null>(null)
const queuedMessageToSendAfterStop = ref<QueuedMessage | null>(null)
let stopQueuedAutoSend: (() => void) | undefined
const {
  data,
  error: sessionError,
  refresh,
  status: sessionStatus
} = useLazyAsyncData(
  () => `web-chat-session-${sessionId.value}`,
  () => api.getSession(sessionId.value),
  { watch: [sessionId] }
)

const isLoadingSession = computed(() => sessionStatus.value === 'idle' || sessionStatus.value === 'pending')
const hasSession = computed(() => Boolean(data.value?.session))
const {
  messages,
  submitStatus,
  streamError,
  chatStatus,
  isRunning,
  connectRun,
  hasConnectedRun,
  cleanupRunMessages
} = useChatRunMessages({
  sessionId,
  refresh,
  refreshSessions,
  refreshSessionOnFinish: false,
  toast,
  activeChatRuns
})
const error = computed(() => streamError.value)
const {
  shouldBlockForMissingWorkspace,
  submitSlashCommandIfNeeded,
  selectSlashCommand,
  onPromptArrowDown,
  onPromptArrowUp,
  onPromptEscape,
  onPromptEnter
} = useChatSlashCommandSubmission({
  api,
  input,
  messages,
  sessionId,
  selectedWorkspace: context.selectedWorkspace,
  selectedModel: composer.selectedModel,
  selectedReasoningEffort: composer.selectedReasoningEffort,
  streamError,
  workspaceInvalidSignal,
  slashCommands,
  toast,
  submitStatus
})
const {
  editingMessageId,
  editingText,
  savingEditedMessageId,
  setEditingMessageContainer,
  resetEditingTextareaLayout,
  startEditingMessage,
  cancelEditingMessage,
  saveEditedMessage
} = useChatMessageEditing({
  api,
  data,
  messages,
  sessionId,
  submitStatus,
  selectedWorkspace: context.selectedWorkspace,
  selectedModel: composer.selectedModel,
  selectedReasoningEffort: composer.selectedReasoningEffort,
  activeChatRuns,
  connectRun,
  rememberLastUsedSelection: composer.rememberLastUsedSelection,
  showError
})

watchEffect(() => {
  activeChatRuns.clearPromptUnread(sessionId.value)
  if (data.value?.session.id !== sessionId.value) {
    messages.value = []
    return
  }

  messages.value = data.value.messages ? [...data.value.messages] : []
})

watch(
  () => data.value?.session,
  async (session) => {
    if (!session || session.id !== sessionId.value) return
    await Promise.all([composer.initializeForSession(session), context.initializeForSession(session)])
  },
  { immediate: true }
)

const title = computed(() => {
  if (isLoadingSession.value) return 'Loading chat…'
  if (sessionError.value || !hasSession.value) return 'Chat unavailable'
  return data.value?.session.title || 'Chat'
})

async function copyUserMessage(message: WebChatMessage) {
  const text = messageText(message)
  if (!text) return

  try {
    await writeClipboardText(text)
    copiedMessageId.value = message.id
    if (copiedMessageTimer) clearTimeout(copiedMessageTimer)
    copiedMessageTimer = setTimeout(() => {
      copiedMessageId.value = null
    }, 1800)
  } catch (err) {
    toast.add({
      color: 'error',
      title: 'Could not copy message',
      description: err instanceof Error ? err.message : String(err)
    })
  }
}

function appendVoiceText(text: string) {
  input.value = input.value ? `${input.value} ${text}` : text
}

function showError(err: unknown, fallback: string) {
  const message = getHermesErrorMessage(err, fallback)
  streamError.value = new Error(message)
  toast.add({ color: 'error', title: fallback, description: message })
}

async function attachFiles(files: File[]) {
  try {
    await context.uploadFiles(files)
  } catch (err) {
    showError(err, 'Could not upload attachment.')
  }
}

function showVoiceError(message: string) {
  showError(new Error(message), 'Voice input failed')
}

async function stopRun() {
  await activeChatRuns.stop(sessionId.value)
}

function warnAttachmentsCannotBeQueued() {
  toast.add({
    color: 'warning',
    title: 'Attachments cannot be queued yet',
    description: 'Wait for the current response to finish, then send the message with attachments.'
  })
}

function enqueueMessage(message: string) {
  if (context.attachments.value.length) {
    warnAttachmentsCannotBeQueued()
    return
  }

  const queued = queuedMessages.enqueue(sessionId.value, message)
  if (queued) input.value = ''
}

async function sendMessageNow(message: string) {
  const pendingAttachments = [...context.attachments.value]
  void prepareNotificationSound()
  input.value = ''
  submitStatus.value = 'submitted'
  const userMessage = createLocalMessage('user', message)
  if (pendingAttachments.length) userMessage.parts.unshift({ type: 'media', attachments: pendingAttachments })
  messages.value.push(userMessage)

  try {
    const run = await api.startRun(message, {
      sessionId: sessionId.value,
      model: composer.selectedModel.value,
      reasoningEffort: composer.selectedReasoningEffort.value,
      workspace: context.selectedWorkspace.value,
      attachments: context.attachments.value.map(attachment => attachment.id)
    })
    composer.rememberLastUsedSelection()
    context.clearAttachments()
    connectRun(run.runId, sessionId.value)
  } catch (err) {
    messages.value = messages.value.filter(message => message.id !== userMessage.id)
    input.value = message
    context.attachments.value = pendingAttachments
    showError(err, 'Failed to send message')
    submitStatus.value = 'error'
    activeChatRuns.markFinished(sessionId.value)
    throw err
  }
}

async function onSubmit() {
  const message = input.value.trim()
  if (!message) return
  if (shouldBlockForMissingWorkspace(message)) return
  if (await submitSlashCommandIfNeeded(message)) return

  if (activeChatRuns.isRunning(sessionId.value) || submitStatus.value === 'submitted') {
    enqueueMessage(message)
    return
  }

  await sendMessageNow(message)
}

function editQueuedMessage(id: string) {
  const queued = queuedForSession.value.find(message => message.id === id)
  if (!queued) return
  input.value = queued.text
  queuedMessages.remove(id)
}

function deleteQueuedMessage(id: string) {
  queuedMessages.remove(id)
}

function isConflictError(err: unknown) {
  const candidate = err as { statusCode?: number, status?: number, response?: { status?: number } }
  return candidate.statusCode === 409 || candidate.status === 409 || candidate.response?.status === 409
}

async function steerViaStopFallback(queued: QueuedMessage) {
  queuedMessageToSendAfterStop.value = queued
  await activeChatRuns.stop(sessionId.value)
  queuedMessages.remove(queued.id)
  toast.add({
    color: 'neutral',
    title: 'Steering after interrupt',
    description: 'Hermes will continue with this message after the current run stops.'
  })
}

async function steerQueuedMessage(id: string) {
  const queued = queuedForSession.value.find(message => message.id === id)
  if (!queued) return

  const runId = activeChatRuns.runIdForSession(sessionId.value)
  if (!runId) {
    if (!activeChatRuns.isRunning(sessionId.value)) {
      queuedMessages.remove(id)
      try {
        await sendMessageNow(queued.text)
      } catch {
        queuedMessages.prepend(queued)
      }
      return
    }

    toast.add({ color: 'warning', title: 'Could not steer run', description: 'The active run is still reconnecting.' })
    return
  }

  steeringQueuedMessageId.value = id
  try {
    await api.steerRun(runId, { text: queued.text })
    queuedMessages.remove(id)
    messages.value.push({
      id: crypto.randomUUID(),
      role: 'system',
      createdAt: new Date().toISOString(),
      parts: [{ type: 'steer', text: queued.text }]
    })
  } catch (err) {
    if (isConflictError(err)) {
      try {
        await steerViaStopFallback(queued)
      } catch (fallbackErr) {
        queuedMessageToSendAfterStop.value = null
        showError(fallbackErr, 'Failed to steer run')
      }
    } else {
      showError(err, 'Failed to steer run')
    }
  } finally {
    steeringQueuedMessageId.value = null
  }
}

async function sendNextQueuedMessage() {
  if (!hasSession.value || activeChatRuns.isRunning(sessionId.value) || submitStatus.value === 'submitted') return

  const priority = queuedMessageToSendAfterStop.value
  if (priority) {
    queuedMessageToSendAfterStop.value = null
    try {
      await sendMessageNow(priority.text)
    } catch {
      queuedMessages.prepend(priority)
    }
    return
  }

  const queued = queuedMessages.shiftForSession(sessionId.value)
  if (!queued) return

  try {
    await sendMessageNow(queued.text)
  } catch {
    queuedMessages.prepend(queued)
  }
}

watch(
  () => data.value?.activeRun,
  (activeRun) => {
    recoverActiveRun({
      sessionId: sessionId.value,
      activeRun,
      hasConnectedRun,
      connectRun
    })
  },
  { immediate: true }
)

watch(
  [sessionId, () => route.query.run],
  ([currentSessionId, queryRun]) => {
    connectRouteRun({
      sessionId: currentSessionId,
      queryRun,
      hasConnectedRun,
      connectRun
    })
  },
  { immediate: true }
)

onMounted(() => {
  stopQueuedAutoSend = activeChatRuns.onFinished(async (finishedSessionId) => {
    if (finishedSessionId !== sessionId.value) return
    await sendNextQueuedMessage()
  })
})

onBeforeUnmount(() => {
  if (copiedMessageTimer) clearTimeout(copiedMessageTimer)
  stopQueuedAutoSend?.()
  cleanupRunMessages()
})
</script>

<template>
  <UDashboardPanel>
    <template #header>
      <AppNavbar :title="title" />
    </template>

    <template #body>
      <UContainer class="mx-auto w-full max-w-[740px] py-6">
        <div v-if="isLoadingSession" class="flex min-h-[40vh] items-center justify-center text-muted">
          <div class="flex items-center gap-2 text-sm">
            <UIcon name="i-lucide-loader-circle" class="size-4 animate-spin" />
            <span>Loading chat…</span>
          </div>
        </div>

        <div v-else-if="sessionError || !hasSession" class="flex min-h-[40vh] items-center justify-center text-center">
          <div class="max-w-sm space-y-3">
            <UIcon name="i-lucide-message-circle-warning" class="mx-auto size-8 text-muted" />
            <div class="space-y-1">
              <h2 class="font-medium text-highlighted">Could not load chat</h2>
              <p class="text-sm text-muted">The chat may have been deleted or the backend is unavailable.</p>
            </div>
            <UButton color="neutral" variant="soft" label="Try again" @click="() => refresh()" />
          </div>
        </div>

        <template v-else>
          <UChatMessages
            :messages="messages"
            :status="chatStatus"
            :shouldAutoScroll="true"
            :shouldScrollToBottom="true"
            :autoScroll="true"
          >
            <template #indicator>
              <div class="flex items-center gap-2 overflow-hidden text-muted">
                <UIcon name="i-lucide-loader-circle" class="size-4 shrink-0 animate-spin" />
                <UChatShimmer text="Thinking…" class="rainbow-chat-shimmer text-sm" />
              </div>
            </template>

            <template #content="{ message }: { message: WebChatMessage }">
              <ChatMessageContent
                v-model:editing-text="editingText"
                :message="message"
                :copied-message-id="copiedMessageId"
                :editing-message-id="editingMessageId"
                :saving-edited-message-id="savingEditedMessageId"
                :is-running="isRunning"
                :set-editing-message-container="setEditingMessageContainer"
                @copy="copyUserMessage"
                @edit="startEditingMessage"
                @cancel-edit="cancelEditingMessage"
                @save-edit="saveEditedMessage"
              />
            </template>
          </UChatMessages>
        </template>
      </UContainer>
    </template>

    <template #footer>
      <UContainer class="mx-auto w-full max-w-[740px] pb-4 sm:pb-6">
        <div v-if="sessionError || (!isLoadingSession && !hasSession)" class="flex min-h-36 items-center justify-center">
          <UButton to="/" color="neutral" variant="soft" icon="i-lucide-plus" label="Start a new chat" />
        </div>

        <div v-else class="space-y-2">
          <ChatQueuedMessages
            v-if="queuedForSession.length"
            :messages="queuedForSession"
            :steering-id="steeringQueuedMessageId"
            :disabled="isLoadingSession || !hasSession"
            @edit="editQueuedMessage"
            @delete="deleteQueuedMessage"
            @steer="steerQueuedMessage"
          />

          <UChatPrompt
            v-model="input"
            :aria-hidden="isLoadingSession"
            :class="isLoadingSession ? 'pointer-events-none invisible' : undefined"
            :error="error || context.contextError.value"
            @submit="onSubmit"
            @keydown.down="onPromptArrowDown"
            @keydown.up="onPromptArrowUp"
            @keydown.esc="onPromptEscape"
            @keydown.enter="onPromptEnter"
          >
            <template #footer>
              <ChatPromptFooter
                :submit-status="chatStatus"
                :workspaces="context.workspaces.value"
                :selected-workspace="context.selectedWorkspace.value"
                :workspace-invalid-signal="workspaceInvalidSignal"
                :workspaces-loading="context.workspacesLoading.value"
                :attachments="context.attachments.value"
                :attachments-loading="context.attachmentsLoading.value"
                :models="composer.models.value"
                :selected-model="composer.selectedModel.value"
                :selected-reasoning-effort="composer.selectedReasoningEffort.value"
                :capabilities-loading="composer.capabilitiesLoading.value"
                :slash-commands="slashCommands.filteredCommands.value"
                :slash-commands-open="slashCommands.isOpen.value"
                :slash-commands-loading="slashCommands.loading.value"
                :highlighted-slash-command-index="slashCommands.highlightedIndex.value"
                @stop="stopRun"
                @update-selected-workspace="context.selectWorkspace"
                @attach-files="attachFiles"
                @remove-attachment="context.removeAttachment"
                @voice-text="appendVoiceText"
                @voice-error="showVoiceError"
                @update-selected-model="composer.selectedModel.value = $event"
                @update-selected-reasoning-effort="composer.selectedReasoningEffort.value = $event"
                @select-slash-command="selectSlashCommand"
                @highlight-slash-command="slashCommands.highlightedIndex.value = $event"
              />
            </template>
          </UChatPrompt>
        </div>
      </UContainer>
    </template>
  </UDashboardPanel>
</template>
