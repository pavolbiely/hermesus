<script setup lang="ts">
import { prepareNotificationSound } from '../../utils/notificationSound'
import { requiresWorkspaceBeforeSubmit } from '../../utils/slashCommands'
import type { ExecuteCommandResponse, WebChatCommand, WebChatMessage, WebChatPart } from '~/types/web-chat'
import { messageText } from '~/utils/chatMessages'
import { writeClipboardText } from '~/utils/clipboard'
import { toolDisplayName } from '~/utils/toolCalls'

const route = useRoute()
const api = useHermesApi()
const composer = useChatComposerCapabilities()
const activeChatRuns = useActiveChatRuns()
const context = useChatComposerContext()
const toast = useToast()
const input = ref('')
const slashCommands = useSlashCommands({ input })
const messages = ref<WebChatMessage[]>([])
const bottomRef = ref<HTMLElement | null>(null)
const autoScrollEnabled = ref(true)
const copiedMessageId = ref<string | null>(null)
const editingMessageId = ref<string | null>(null)
const editingText = ref('')
const editingMessageContainer = ref<HTMLElement | null>(null)
const editingMessageBubble = ref<HTMLElement | null>(null)
const editingMessageRow = ref<HTMLElement | null>(null)
const savingEditedMessageId = ref<string | null>(null)
const submitStatus = ref<'ready' | 'submitted' | 'streaming' | 'error'>('ready')
const streamError = ref<Error | undefined>()
const workspaceInvalidSignal = ref(0)
const connectedRunIds = new Set<string>()
let copiedMessageTimer: ReturnType<typeof setTimeout> | undefined
let unsubscribeRun: (() => void) | undefined
const error = computed(() => streamError.value)
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
const chatStatus = computed(() => submitStatus.value === 'submitted' || activeChatRuns.isRunning(sessionId.value) ? 'streaming' : 'ready')
const isRunning = computed(() => activeChatRuns.isRunning(sessionId.value))

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

function isThinkingMessage(message: WebChatMessage) {
  return message.role === 'assistant' && message.parts.some(part => part.status === 'thinking') && isRunning.value
}

function createThinkingMessage() {
  const message = createLocalMessage('assistant', '')
  message.parts = [{ type: 'text', text: '', status: 'thinking' }]
  return message
}

function ensureThinkingMessage() {
  const lastMessage = messages.value.at(-1)
  if (lastMessage?.role === 'assistant') return
  messages.value.push(createThinkingMessage())
}

function scrollToBottom(behavior: ScrollBehavior = 'smooth') {
  if (!autoScrollEnabled.value) return
  bottomRef.value?.scrollIntoView({ block: 'end', behavior })
}

function isNearBottom() {
  const scrollTop = window.scrollY || document.documentElement.scrollTop
  return window.innerHeight + scrollTop >= document.documentElement.scrollHeight - 80
}

const scrollKeys = new Set(['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '])

function pauseAutoScroll(event?: Event) {
  if (!isRunning.value) return
  if (event instanceof KeyboardEvent && !scrollKeys.has(event.key)) return
  if (event?.type === 'scroll' && isNearBottom()) return
  autoScrollEnabled.value = false
}

function scheduleAutoScroll(behavior: ScrollBehavior = 'smooth') {
  nextTick(() => scrollToBottom(behavior))
}

function appendAssistantDelta(content: string) {
  if (!content) return

  let assistant = messages.value[messages.value.length - 1]
  if (!assistant || assistant.role !== 'assistant') {
    assistant = createLocalMessage('assistant', '')
    messages.value.push(assistant)
  }

  const textPart = assistant.parts.find(part => part.type === 'text')
  if (textPart) {
    textPart.text = textPart.status === 'thinking' ? content : `${textPart.text || ''}${content}`
    textPart.status = null
  } else {
    assistant.parts.push({ type: 'text', text: content })
  }

  scheduleAutoScroll()
}

function replaceAssistantMessage(content?: string) {
  if (!content) return

  const assistant = messages.value[messages.value.length - 1]
  if (assistant?.role === 'assistant') {
    assistant.parts = [{ type: 'text', text: content, status: null }]
    scheduleAutoScroll()
  }
}

function appendToolStarted(payload: { name?: string, preview?: string, input?: unknown }) {
  let assistant = messages.value[messages.value.length - 1]
  if (!assistant || assistant.role !== 'assistant') {
    assistant = createLocalMessage('assistant', '')
    messages.value.push(assistant)
  }

  const thinkingIndex = assistant.parts.findIndex(part => part.status === 'thinking')
  if (thinkingIndex >= 0) assistant.parts.splice(thinkingIndex, 1)

  const toolPart: WebChatPart = {
    type: 'tool',
    name: payload.name,
    status: 'running',
    input: payload.input ?? payload.preview ?? null
  }
  toolPart.name = toolDisplayName(toolPart)
  assistant.parts.push(toolPart)
  scheduleAutoScroll()
}

function markToolCompleted(payload: { name?: string }) {
  const assistant = [...messages.value].reverse().find(message => message.role === 'assistant')
  const toolPart = assistant?.parts.findLast(part => part.type === 'tool' && part.status === 'running' && (!payload.name || part.name === payload.name))
  if (toolPart) toolPart.status = 'completed'
}

function connectRun(runId: string, targetSessionId = sessionId.value) {
  connectedRunIds.add(runId)
  const tracked = activeChatRuns.trackRun(targetSessionId, runId)
  if (!tracked) {
    submitStatus.value = 'ready'
    void refresh()
    void refreshSessions?.()
    return
  }

  if (targetSessionId === sessionId.value) {
    submitStatus.value = 'streaming'
    ensureThinkingMessage()
    scheduleAutoScroll()
  }

  unsubscribeRun?.()
  unsubscribeRun = activeChatRuns.subscribe(targetSessionId, {
    onDelta: (content) => {
      if (targetSessionId === sessionId.value) appendAssistantDelta(content)
    },
    onCompleted: (content) => {
      if (targetSessionId === sessionId.value) replaceAssistantMessage(content)
    },
    onToolStarted: (payload) => {
      if (targetSessionId === sessionId.value) appendToolStarted(payload)
    },
    onToolCompleted: (payload) => {
      if (targetSessionId === sessionId.value) markToolCompleted(payload)
    },
    onError: (err) => {
      if (targetSessionId !== sessionId.value) return
      streamError.value = err
      submitStatus.value = 'error'
      toast.add({ color: 'error', title: 'Run failed', description: err.message })
    },
    async onFinished() {
      if (targetSessionId === sessionId.value) {
        submitStatus.value = 'ready'
        await refresh()
      }
      await refreshSessions?.()
    }
  })
}

watch(
  () => [route.query.run, data.value?.session.id] as const,
  ([runId]) => {
    const targetSessionId = data.value?.session.id
    if (typeof runId !== 'string' || !targetSessionId || connectedRunIds.has(runId) || targetSessionId !== sessionId.value) return
    autoScrollEnabled.value = true
    connectRun(runId, targetSessionId)
  },
  { immediate: true }
)

function appendVoiceText(text: string) {
  input.value = input.value ? `${input.value} ${text}` : text
}

function showError(err: unknown, fallback: string) {
  const message = getHermesErrorMessage(err, fallback)
  streamError.value = new Error(message)
  toast.add({ color: 'error', title: fallback, description: message })
}

function showCommandError(err: unknown, commandText: string) {
  const message = getHermesErrorMessage(err, 'Command failed')
  toast.add({ color: 'warning', title: commandText, description: message })
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

function messageAttachmentIds(message: WebChatMessage) {
  return message.parts
    .flatMap(part => part.type === 'media' ? part.attachments || [] : [])
    .map(attachment => attachment.id)
}

function setEditingMessageContainer(el: unknown) {
  editingMessageContainer.value = el instanceof HTMLElement ? el : null
}

function appendCommandResponse(commandText: string, response: ExecuteCommandResponse) {
  messages.value.push({
    id: `command-user-${Date.now()}`,
    role: 'user',
    createdAt: new Date().toISOString(),
    parts: [{ type: 'text', text: commandText }]
  })
  if (response.message) {
    if (response.changes) response.message.parts.push({ type: 'changes', changes: response.changes })
    messages.value.push(response.message)
  }
  scheduleAutoScroll()
}

function shouldBlockForMissingWorkspace(message: string) {
  if (!requiresWorkspaceBeforeSubmit(message, context.selectedWorkspace.value)) return false
  workspaceInvalidSignal.value += 1
  return true
}

async function executeSlashCommand(commandText: string) {
  if (shouldBlockForMissingWorkspace(commandText)) return false

  streamError.value = undefined
  try {
    const response = await api.executeCommand({
      command: commandText,
      sessionId: sessionId.value,
      workspace: context.selectedWorkspace.value,
      model: composer.selectedModel.value,
      reasoningEffort: composer.selectedReasoningEffort.value
    })
    appendCommandResponse(commandText, response)
  } catch (err) {
    showCommandError(err, commandText)
  }
  return true
}

async function submitSlashCommandIfNeeded(message: string) {
  if (!message.startsWith('/')) return false
  await slashCommands.loadCommands()
  const command = slashCommands.exactCommand(message)
  if (!command) return false
  const executed = await executeSlashCommand(command.name)
  if (executed) input.value = ''
  return true
}

async function selectSlashCommand(command: WebChatCommand) {
  input.value = command.name
  const executed = await executeSlashCommand(command.name)
  if (executed) input.value = ''
}

function onPromptArrowDown(event: KeyboardEvent) {
  if (!slashCommands.isOpen.value) return
  event.preventDefault()
  slashCommands.moveHighlight(1)
}

function onPromptArrowUp(event: KeyboardEvent) {
  if (!slashCommands.isOpen.value) return
  event.preventDefault()
  slashCommands.moveHighlight(-1)
}

function onPromptEscape(event: KeyboardEvent) {
  if (!slashCommands.isOpen.value) return
  event.preventDefault()
  event.stopPropagation()
  slashCommands.close()
}

function onPromptEnter(event: KeyboardEvent) {
  if (!slashCommands.isOpen.value) return
  const command = slashCommands.highlightedCommand()
  if (!command) return
  event.preventDefault()
  selectSlashCommand(command)
}

function resetEditingTextareaLayout() {
  if (editingMessageContainer.value) {
    editingMessageContainer.value.style.width = ''
    editingMessageContainer.value.style.marginLeft = ''
  }

  if (editingMessageBubble.value) {
    editingMessageBubble.value.style.width = ''
    editingMessageBubble.value = null
  }

  if (editingMessageRow.value) {
    editingMessageRow.value.style.width = ''
    editingMessageRow.value.style.maxWidth = ''
    editingMessageRow.value.style.transform = ''
    editingMessageRow.value = null
  }
}

function alignEditingTextareaWithPrompt() {
  const container = editingMessageContainer.value
  const promptTextarea = document.querySelector<HTMLTextAreaElement>('textarea[placeholder="Type your message here…"]')
  const promptRoot = promptTextarea?.closest<HTMLElement>('[data-slot="root"]')
  const bubble = container?.parentElement
  const row = bubble?.parentElement
  if (!container || !promptRoot || !bubble || !row) return

  const promptRect = promptRoot.getBoundingClientRect()
  const bubbleStyle = getComputedStyle(bubble)
  const bubblePaddingLeft = parseFloat(bubbleStyle.paddingLeft) || 0
  const bubblePadding = bubblePaddingLeft + (parseFloat(bubbleStyle.paddingRight) || 0)
  const bubbleWidth = promptRect.width + bubblePadding

  editingMessageBubble.value = bubble
  editingMessageRow.value = row
  row.style.width = `${bubbleWidth}px`
  row.style.maxWidth = 'none'
  row.style.transform = `translateX(-${bubblePaddingLeft}px)`
  bubble.style.width = `${bubbleWidth}px`
  container.style.width = `${promptRect.width}px`
  container.style.marginLeft = '0'
}

async function focusEditingTextarea() {
  await nextTick()
  alignEditingTextareaWithPrompt()
  const textarea = editingMessageContainer.value?.querySelector('textarea')
  if (!textarea) return
  textarea.focus()
  const end = textarea.value.length
  textarea.setSelectionRange(end, end)
}

function startEditingMessage(message: WebChatMessage) {
  if (activeChatRuns.isRunning(sessionId.value) || submitStatus.value === 'submitted') return
  resetEditingTextareaLayout()
  editingMessageId.value = message.id
  editingText.value = messageText(message)
  void focusEditingTextarea()
}

function cancelEditingMessage() {
  resetEditingTextareaLayout()
  editingMessageId.value = null
  editingText.value = ''
}

async function saveEditedMessage(message: WebChatMessage) {
  const content = editingText.value.trim()
  if (!content || savingEditedMessageId.value || activeChatRuns.isRunning(sessionId.value)) return

  const previousMessages = [...messages.value]
  savingEditedMessageId.value = message.id
  void prepareNotificationSound()

  try {
    const updated = await api.editMessage(sessionId.value, message.id, content)
    data.value = updated
    messages.value = [...updated.messages]
    resetEditingTextareaLayout()
    editingMessageId.value = null
    editingText.value = ''
    submitStatus.value = 'submitted'
    autoScrollEnabled.value = true
    messages.value.push(createThinkingMessage())
    scheduleAutoScroll()

    const attachmentIds = messageAttachmentIds(message)
    const run = await api.startRun(content, {
      sessionId: sessionId.value,
      model: composer.selectedModel.value,
      reasoningEffort: composer.selectedReasoningEffort.value,
      workspace: context.selectedWorkspace.value || undefined,
      attachments: attachmentIds,
      editedMessageId: message.id
    })
    composer.rememberLastUsedSelection()
    connectRun(run.runId, sessionId.value)
  } catch (err) {
    messages.value = previousMessages
    submitStatus.value = 'error'
    activeChatRuns.markFinished(sessionId.value)
    showError(err, 'Failed to edit message')
  } finally {
    savingEditedMessageId.value = null
  }
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
  unsubscribeRun?.()
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
