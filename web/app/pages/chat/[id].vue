<script setup lang="ts">
import { prepareNotificationSound } from '../../utils/notificationSound'
import type { WebChatMessage } from '~/types/web-chat'
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
  bottomRef,
  autoScrollEnabled,
  submitStatus,
  streamError,
  chatStatus,
  isRunning,
  createThinkingMessage,
  isThinkingMessage,
  scheduleAutoScroll,
  pauseAutoScroll,
  connectRun,
  hasConnectedRun,
  cleanupRunMessages
} = useChatRunMessages({
  sessionId,
  refresh,
  refreshSessions,
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
  scheduleAutoScroll
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
  autoScrollEnabled,
  selectedWorkspace: context.selectedWorkspace,
  selectedModel: composer.selectedModel,
  selectedReasoningEffort: composer.selectedReasoningEffort,
  activeChatRuns,
  createThinkingMessage,
  scheduleAutoScroll,
  connectRun,
  rememberLastUsedSelection: composer.rememberLastUsedSelection,
  showError
})

watchEffect(() => {
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

async function onSubmit() {
  const message = input.value.trim()
  if (!message || activeChatRuns.isRunning(sessionId.value) || submitStatus.value === 'submitted') return
  if (shouldBlockForMissingWorkspace(message)) return
  if (await submitSlashCommandIfNeeded(message)) return

  const pendingAttachments = [...context.attachments.value]
  void prepareNotificationSound()
  input.value = ''
  autoScrollEnabled.value = true
  submitStatus.value = 'submitted'
  const userMessage = createLocalMessage('user', message)
  if (pendingAttachments.length) userMessage.parts.unshift({ type: 'media', attachments: pendingAttachments })
  messages.value.push(userMessage)
  messages.value.push(createThinkingMessage())
  scheduleAutoScroll()

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
    if (messages.value.at(-1)?.role === 'assistant' && messages.value.at(-1)?.parts.some(part => part.status === 'thinking')) {
      messages.value.pop()
    }
    messages.value = messages.value.filter(message => message.id !== userMessage.id)
    input.value = message
    context.attachments.value = pendingAttachments
    showError(err, 'Failed to send message')
    submitStatus.value = 'error'
    activeChatRuns.markFinished(sessionId.value)
  }
}

onMounted(() => {
  window.addEventListener('scroll', pauseAutoScroll, { passive: true })
  window.addEventListener('wheel', pauseAutoScroll, { passive: true })
  window.addEventListener('touchmove', pauseAutoScroll, { passive: true })
  window.addEventListener('keydown', pauseAutoScroll)
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', pauseAutoScroll)
  window.removeEventListener('wheel', pauseAutoScroll)
  window.removeEventListener('touchmove', pauseAutoScroll)
  window.removeEventListener('keydown', pauseAutoScroll)
  if (copiedMessageTimer) clearTimeout(copiedMessageTimer)
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
          <UChatMessages :messages="messages" :status="chatStatus">
            <template #content="{ message }: { message: WebChatMessage }">
              <ChatMessageContent
                v-model:editing-text="editingText"
                :message="message"
                :is-thinking="isThinkingMessage(message)"
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
          <div ref="bottomRef" class="h-px" aria-hidden="true" />
        </template>
      </UContainer>
    </template>

    <template #footer>
      <UContainer class="mx-auto w-full max-w-[740px] pb-4 sm:pb-6">
        <div v-if="sessionError || (!isLoadingSession && !hasSession)" class="flex min-h-36 items-center justify-center">
          <UButton to="/" color="neutral" variant="soft" icon="i-lucide-plus" label="Start a new chat" />
        </div>

        <UChatPrompt
          v-else
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
      </UContainer>
    </template>
  </UDashboardPanel>
</template>
