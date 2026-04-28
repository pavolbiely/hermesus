<script setup lang="ts">
import { playNotificationSound, prepareNotificationSound } from '../../utils/notificationSound'
import { recoverActiveRun } from '../../utils/activeRunRecovery'
import { connectRouteRun } from '../../utils/routeRunConnection'
import type { SessionDetailResponse, WebChatAttachment, WebChatMessage } from '~/types/web-chat'
import type { QueuedMessage } from '~/utils/queuedMessages'
import { latestChangePartKey, messageText } from '~/utils/chatMessages'
import { filesFromClipboard, writeClipboardText } from '~/utils/clipboard'
import { mergeOptimisticUserMessages } from '~/utils/optimisticChatMessages'
import { markLocalMessageFailed, markLocalMessageSending, removeLocalMessage } from '~/utils/failedChatMessages'
import { scrollElementTreeToBottom, scrollElementTreeToBottomAfterRender, nearestScrollableAncestor, isElementVisibleInRoot } from '~/utils/chatInitialScroll'
import { loadingChatSkeletonCount } from '~/utils/chatLoadingState'

const INITIAL_SESSION_MESSAGE_LIMIT = 60
const OLDER_SESSION_MESSAGE_LIMIT = 80

const route = useRoute()
const sessionId = computed(() => String(route.params.id))
const api = useHermesApi()
const sessionCache = useWebChatSessionCache(api)
const composer = useChatComposerCapabilities()
const activeChatRuns = useActiveChatRuns()
const context = useChatComposerContext()
const toast = useToast()
const { input } = useChatDraft(sessionId)
const chatContainer = ref<HTMLElement | null>(null)
const bottomReadSentinel = ref<HTMLElement | null>(null)
const olderMessagesSentinel = ref<HTMLElement | null>(null)
const initialScrollSettledSessionId = ref<string | null>(null)
const lastRenderedMessageCount = ref(0)
const loadingSkeletonCount = computed(() => loadingChatSkeletonCount(lastRenderedMessageCount.value))
const slashCommands = useSlashCommands({ input })
const copiedMessageId = ref<string | null>(null)
const workspaceInvalidSignal = ref(0)
const suppressNextInterruptedMessage = ref(false)
const loadingOlderMessages = ref(false)
const olderMessagesError = ref<string | null>(null)
let preserveScrollAfterPrepend: { root: Element, previousScrollHeight: number, previousScrollTop: number } | null = null
let copiedMessageTimer: ReturnType<typeof setTimeout> | undefined
const refreshSessions = inject<() => Promise<void> | void>('refreshSessions')
const markSessionRead = inject<(sessionId: string, messageCount: number) => void>('markSessionRead')
let optimisticUserMessageIds = new Set<string>()
let bottomReadObserver: IntersectionObserver | undefined
let olderMessagesObserver: IntersectionObserver | undefined
let olderMessagesScrollRoot: Element | null = null
let readScrollRoot: Element | null = null
let readScrollAnimationFrame: number | undefined
let previousScrollRestoration: ScrollRestoration | undefined

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
  async () => {
    const response = await sessionCache.fetch(sessionId.value, { messageLimit: INITIAL_SESSION_MESSAGE_LIMIT })
    sessionCache.set(response)
    return response
  },
  {
    watch: [sessionId]
  }
)

const displayedData = computed(() => {
  if (data.value?.session.id === sessionId.value) return data.value
  return sessionCache.get(sessionId.value)
})
const hasOlderMessages = computed(() => Boolean(displayedData.value?.messagesHasMoreBefore))
const olderMessagesLabel = computed(() => {
  const total = displayedData.value?.messagesTotal
  if (!total) return 'Load earlier messages'
  return `Load earlier messages (${messages.value.length}/${total})`
})
const isLoadingSession = computed(() => (sessionStatus.value === 'idle' || sessionStatus.value === 'pending') && !displayedData.value)
const hasSession = computed(() => Boolean(displayedData.value?.session))
const {
  messages,
  submitStatus,
  streamError,
  chatStatus,
  currentActivityLabel,
  isRunning,
  connectRun,
  hasConnectedRun,
  cleanupRunMessages
} = useChatRunMessages({
  sessionId,
  refresh,
  refreshSessions,
  refreshSessionOnFinish: false,
  shouldSuppressCompleted: (payload) => {
    if (!suppressNextInterruptedMessage.value || payload.content !== 'Chat interrupted.') return false
    suppressNextInterruptedMessage.value = false
    return true
  },
  toast,
  activeChatRuns
})
const error = computed(() => streamError.value)
const latestGitChangePartKey = computed(() => latestChangePartKey(messages.value))
const chatMessagesStatus = computed(() => chatStatus.value === 'submitted' ? 'streaming' : chatStatus.value)
const showRunActivityIndicator = computed(() => Boolean(currentActivityLabel.value))
const promptContextUsage = computed(() => {
  const model = composer.models.value.find(model => model.id === composer.selectedModel.value)
  if (!model?.contextWindowTokens || !model.autoCompressTokens) return null

  return {
    usedTokens: latestMeasuredContextTokens(),
    maxTokens: model.contextWindowTokens,
    autoCompressTokens: model.autoCompressTokens
  }
})
const {
  selectSlashCommand,
  onPromptArrowDown,
  onPromptArrowUp,
  onPromptEscape,
  onPromptEnter: onPromptAutocompleteEnter
} = useChatSlashCommandAutocomplete({
  input,
  slashCommands
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
  onInterruptingForEdit: () => {
    suppressNextInterruptedMessage.value = true
  },
  showError
})

watch(
  data,
  (response) => {
    if (response?.session.id === sessionId.value) sessionCache.set(response)
  },
  { immediate: true }
)

watch(
  [sessionId, () => displayedData.value?.session.id, () => displayedData.value?.messages],
  ([currentSessionId, loadedSessionId, persistedMessages]) => {
    if (loadedSessionId !== currentSessionId) {
      messages.value = []
      optimisticUserMessageIds = new Set()
      return
    }

    const merged = mergeOptimisticUserMessages(
      persistedMessages ? [...persistedMessages] : [],
      messages.value,
      optimisticUserMessageIds,
      { preserveStreamingAssistant: activeChatRuns.isRunning(currentSessionId) }
    )
    messages.value = merged.messages
    optimisticUserMessageIds = merged.optimisticMessageIds
    lastRenderedMessageCount.value = messages.value.length
  },
  { immediate: true }
)

watch(sessionId, () => {
  initialScrollSettledSessionId.value = null
})

watch(
  () => [displayedData.value?.session.id, messages.value.length] as const,
  async ([loadedSessionId]) => {
    if (loadedSessionId !== sessionId.value) return
    if (initialScrollSettledSessionId.value === loadedSessionId) return

    if (typeof requestAnimationFrame !== 'function') {
      initialScrollSettledSessionId.value = loadedSessionId
      return
    }

    await scrollChatToBottomAfterRender()
    attachReadScrollListener()
    attachOlderMessagesObserver()
    initialScrollSettledSessionId.value = loadedSessionId
  },
  { immediate: true, flush: 'post' }
)

watch(
  () => displayedData.value?.session,
  async (session) => {
    if (!session || session.id !== sessionId.value) return
    await Promise.all([composer.initializeForSession(session), context.initializeForSession(session)])
  },
  { immediate: true }
)

const title = computed(() => {
  if (isLoadingSession.value) return 'Loading chat…'
  if (sessionError.value || !hasSession.value) return 'Chat unavailable'
  return displayedData.value?.session.title || 'Chat'
})

function latestMeasuredContextTokens() {
  for (let index = messages.value.length - 1; index >= 0; index -= 1) {
    const message = messages.value[index]
    if (message?.role !== 'assistant') continue

    const measured = [message.inputTokens, message.outputTokens]
      .filter((value): value is number => typeof value === 'number' && Number.isFinite(value) && value > 0)
      .reduce((total, value) => total + value, 0)

    if (measured > 0) return measured
  }

  return 0
}

function pathBaseName(path?: string | null) {
  if (!path) return null
  return path.split(/[\\/]+/).filter(Boolean).at(-1) || path
}

const workspaceStatus = computed(() => {
  const workspace = displayedData.value?.isolatedWorkspace
  if (!workspace || workspace.status !== 'active') return null

  const sourceName = pathBaseName(workspace.sourceWorkspace)
  const branchName = workspace.branchName.split('/').at(-1)
  return {
    label: sourceName ? `${sourceName} · worktree` : 'Worktree',
    detail: `${workspace.worktreePath}${branchName ? `\n${branchName}` : ''}`
  }
})

async function copyMessage(message: WebChatMessage) {
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

async function onPromptPaste(event: ClipboardEvent) {
  const files = filesFromClipboard(event)
  if (!files.length) return

  event.preventDefault()
  if (chatStatus.value === 'submitted' || chatStatus.value === 'streaming' || context.attachmentsLoading.value) {
    toast.add({ color: 'warning', title: 'Attachment upload is unavailable right now' })
    return
  }

  await attachFiles(files)
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

function visibleMessageCount() {
  return Math.max(displayedData.value?.session.messageCount || 0, messages.value.length)
}

function latestMessageElement() {
  return chatContainer.value?.querySelector('article:last-of-type') ?? null
}

function readVisibilityRoot() {
  return nearestScrollableAncestor(chatContainer.value)
}

function mergeOlderSessionMessages(current: SessionDetailResponse, older: SessionDetailResponse): SessionDetailResponse {
  const seen = new Set(current.messages.map(message => message.id))
  const olderMessages = older.messages.filter(message => !seen.has(message.id))
  return {
    ...current,
    session: older.session,
    messages: [...olderMessages, ...current.messages],
    messagesHasMoreBefore: older.messagesHasMoreBefore,
    messagesTotal: older.messagesTotal ?? current.messagesTotal
  }
}

function preserveCurrentScrollPosition() {
  const root = readVisibilityRoot()
  if (!root) return
  preserveScrollAfterPrepend = {
    root,
    previousScrollHeight: root.scrollHeight,
    previousScrollTop: root.scrollTop
  }
}

async function restoreScrollPositionAfterPrepend() {
  const preserved = preserveScrollAfterPrepend
  preserveScrollAfterPrepend = null
  if (!preserved) return
  await nextTick()
  await waitForAnimationFrame()
  preserved.root.scrollTop = preserved.previousScrollTop + (preserved.root.scrollHeight - preserved.previousScrollHeight)
}

async function loadOlderMessages() {
  if (loadingOlderMessages.value || !hasOlderMessages.value) return
  if (initialScrollSettledSessionId.value !== sessionId.value) return
  const current = displayedData.value
  const beforeMessageId = current?.messages[0]?.id
  if (!current || current.session.id !== sessionId.value || !beforeMessageId) return

  loadingOlderMessages.value = true
  olderMessagesError.value = null
  preserveCurrentScrollPosition()

  try {
    const older = await sessionCache.fetch(sessionId.value, {
      messageLimit: OLDER_SESSION_MESSAGE_LIMIT,
      messageBefore: beforeMessageId
    })
    const merged = mergeOlderSessionMessages(current, older)
    data.value = merged
    sessionCache.set(merged)
    await restoreScrollPositionAfterPrepend()
  } catch (err) {
    preserveScrollAfterPrepend = null
    olderMessagesError.value = getHermesErrorMessage(err, 'Could not load earlier messages')
  } finally {
    loadingOlderMessages.value = false
  }
}

function attachOlderMessagesObserver() {
  if (typeof IntersectionObserver !== 'function') return
  const nextRoot = readVisibilityRoot()
  if (olderMessagesObserver && olderMessagesScrollRoot === nextRoot) return

  olderMessagesObserver?.disconnect()
  olderMessagesScrollRoot = nextRoot
  olderMessagesObserver = new IntersectionObserver((entries) => {
    if (entries.some(entry => entry.isIntersecting)) void loadOlderMessages()
  }, { root: nextRoot, rootMargin: '240px 0px 0px 0px', threshold: 0 })

  if (olderMessagesSentinel.value) olderMessagesObserver.observe(olderMessagesSentinel.value)
}

function isBottomReadSentinelVisible() {
  return isElementVisibleInRoot(bottomReadSentinel.value, readVisibilityRoot())
}

function isLatestMessageVisible() {
  return isElementVisibleInRoot(latestMessageElement(), readVisibilityRoot())
}

function markCurrentSessionReadIfVisible() {
  if (!markSessionRead || displayedData.value?.session.id !== sessionId.value) return
  if (!isBottomReadSentinelVisible() && !isLatestMessageVisible()) return

  markSessionRead(sessionId.value, visibleMessageCount())
  activeChatRuns.clearPromptUnread(sessionId.value)
}

function scheduleReadVisibilityCheck() {
  if (typeof requestAnimationFrame !== 'function') {
    markCurrentSessionReadIfVisible()
    return
  }

  if (readScrollAnimationFrame !== undefined) return
  readScrollAnimationFrame = requestAnimationFrame(() => {
    readScrollAnimationFrame = undefined
    markCurrentSessionReadIfVisible()
  })
}

function attachReadScrollListener() {
  const nextRoot = readVisibilityRoot()
  if (nextRoot === readScrollRoot) return
  readScrollRoot?.removeEventListener('scroll', scheduleReadVisibilityCheck)
  readScrollRoot = nextRoot
  readScrollRoot?.addEventListener('scroll', scheduleReadVisibilityCheck, { passive: true })
}

function waitForAnimationFrame() {
  if (typeof requestAnimationFrame !== 'function') return Promise.resolve()
  return new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
}

async function scrollChatToBottomAfterRender() {
  await scrollElementTreeToBottomAfterRender(chatContainer.value, {
    waitForDomUpdate: nextTick,
    waitForFrame: waitForAnimationFrame,
    frameCount: 3
  })

  for (const delay of [100, 350]) {
    await new Promise<void>(resolve => setTimeout(resolve, delay))
    scrollElementTreeToBottom(chatContainer.value)
  }

  markCurrentSessionReadIfVisible()
}

async function startRunForLocalMessage(
  userMessage: WebChatMessage,
  text: string,
  clientMessageId: string,
  attachmentIds: string[]
) {
  try {
    const run = await api.startRun(text, {
      sessionId: sessionId.value,
      model: composer.selectedModel.value,
      reasoningEffort: composer.selectedReasoningEffort.value,
      workspace: context.selectedWorkspace.value,
      attachments: attachmentIds,
      clientMessageId
    })
    const canonicalId = run.userMessageId || userMessage.id
    optimisticUserMessageIds.delete(userMessage.id)
    optimisticUserMessageIds.add(canonicalId)
    const sentMessage = {
      ...userMessage,
      id: canonicalId,
      localStatus: undefined,
      localError: undefined
    }
    Object.assign(userMessage, sentMessage)
    messages.value = messages.value.map(message => message.id === userMessage.id || message.clientMessageId === clientMessageId ? sentMessage : message)
    composer.rememberLastUsedSelection()
    playNotificationSound('sent')
    void refreshSessions?.()
    connectRun(run.runId, sessionId.value)
    void scrollChatToBottomAfterRender()
  } catch (err) {
    const errorMessage = getHermesErrorMessage(err, 'Not sent')
    messages.value = markLocalMessageFailed(messages.value, userMessage.id, errorMessage)
    showError(err, 'Failed to send message')
    submitStatus.value = 'error'
    activeChatRuns.markFinished(sessionId.value)
    throw err
  }
}

async function sendMessageNow(message: string) {
  const pendingAttachments = [...context.attachments.value]
  void prepareNotificationSound()
  input.value = ''
  submitStatus.value = 'submitted'
  const clientMessageId = crypto.randomUUID()
  const userMessage = createLocalMessage('user', message)
  userMessage.clientMessageId = clientMessageId
  userMessage.localStatus = 'sending'
  optimisticUserMessageIds.add(userMessage.id)
  if (pendingAttachments.length) userMessage.parts.unshift({ type: 'media', attachments: pendingAttachments })
  messages.value.push(userMessage)
  context.clearAttachments()
  void scrollChatToBottomAfterRender()

  await startRunForLocalMessage(
    userMessage,
    message,
    clientMessageId,
    pendingAttachments.map(attachment => attachment.id)
  )
}

function attachmentsForMessage(message: WebChatMessage): WebChatAttachment[] {
  return message.parts.flatMap(part => part.type === 'media' ? part.attachments || [] : [])
}

function attachmentIdsForMessage(message: WebChatMessage) {
  return attachmentsForMessage(message).map(attachment => attachment.id)
}

function previousUserMessage(message: WebChatMessage) {
  const messageIndex = messages.value.findIndex(item => item.id === message.id)
  if (messageIndex <= 0) return null

  for (let index = messageIndex - 1; index >= 0; index -= 1) {
    const candidate = messages.value[index]
    if (candidate?.role === 'user') return candidate
  }

  return null
}

async function regenerateResponse(message: WebChatMessage) {
  if (message.role !== 'assistant') return
  if (activeChatRuns.isRunning(sessionId.value) || submitStatus.value === 'submitted') return

  const userMessage = previousUserMessage(message)
  const content = userMessage ? messageText(userMessage).trim() : ''
  if (!userMessage || !content) {
    toast.add({ color: 'warning', title: 'Could not find the prompt to regenerate.' })
    return
  }

  const previousData = data.value || displayedData.value || undefined
  const previousMessages = [...messages.value]
  void prepareNotificationSound()
  submitStatus.value = 'submitted'

  try {
    const updated = await api.editMessage(sessionId.value, userMessage.id, content)
    data.value = updated
    sessionCache.set(updated)
    messages.value = [...updated.messages]

    const run = await api.startRun(content, {
      sessionId: sessionId.value,
      model: composer.selectedModel.value,
      reasoningEffort: composer.selectedReasoningEffort.value,
      workspace: context.selectedWorkspace.value,
      attachments: attachmentIdsForMessage(userMessage),
      editedMessageId: userMessage.id
    })
    composer.rememberLastUsedSelection()
    playNotificationSound('sent')
    void refreshSessions?.()
    connectRun(run.runId, sessionId.value)
    void scrollChatToBottomAfterRender()
  } catch (err) {
    data.value = previousData
    sessionCache.set(previousData)
    messages.value = previousMessages
    submitStatus.value = 'error'
    activeChatRuns.markFinished(sessionId.value)
    showError(err, 'Failed to regenerate response')
  }
}

async function retryFailedMessage(message: WebChatMessage) {
  if (message.localStatus !== 'failed') return
  const text = messageText(message).trim()
  if (!text || !message.clientMessageId) return
  if (activeChatRuns.isRunning(sessionId.value) || submitStatus.value === 'submitted') {
    enqueueMessage(text)
    messages.value = removeLocalMessage(messages.value, message.id)
    optimisticUserMessageIds.delete(message.id)
    return
  }

  messages.value = markLocalMessageSending(messages.value, message.id)
  const retryMessage = messages.value.find(item => item.id === message.id) || message
  submitStatus.value = 'submitted'
  try {
    await startRunForLocalMessage(
      retryMessage,
      text,
      message.clientMessageId,
      attachmentIdsForMessage(message)
    )
  } catch {
    // startRunForLocalMessage keeps the failed bubble visible and shows the toast.
  }
}

function editFailedMessage(message: WebChatMessage) {
  input.value = messageText(message)
  context.attachments.value = attachmentsForMessage(message)
  messages.value = removeLocalMessage(messages.value, message.id)
  optimisticUserMessageIds.delete(message.id)
}

async function onSubmit() {
  const message = input.value.trim()
  if (!message) return
  if (!context.selectedWorkspace.value) {
    workspaceInvalidSignal.value += 1
    return
  }

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
  () => displayedData.value?.activeRun,
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
  () => [sessionId.value, messages.value.length] as const,
  async () => {
    await nextTick()
    attachReadScrollListener()
    markCurrentSessionReadIfVisible()
  },
  { flush: 'post' }
)

watch(
  bottomReadSentinel,
  (sentinel, previous) => {
    if (!bottomReadObserver) return
    if (previous) bottomReadObserver.unobserve(previous)
    if (sentinel) bottomReadObserver.observe(sentinel)
  },
  { flush: 'post' }
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
  if (history.scrollRestoration) {
    previousScrollRestoration = history.scrollRestoration
    history.scrollRestoration = 'manual'
  }

  if (typeof IntersectionObserver === 'function') {
    bottomReadObserver = new IntersectionObserver((entries) => {
      if (entries.some(entry => entry.isIntersecting)) markCurrentSessionReadIfVisible()
    }, { root: readVisibilityRoot(), threshold: 0 })

    if (bottomReadSentinel.value) bottomReadObserver.observe(bottomReadSentinel.value)
  }

  attachReadScrollListener()

  stopQueuedAutoSend = activeChatRuns.onFinished(async (finishedSessionId) => {
    if (finishedSessionId !== sessionId.value) return
    await sendNextQueuedMessage()
  })
})

onBeforeUnmount(() => {
  if (copiedMessageTimer) clearTimeout(copiedMessageTimer)
  if (previousScrollRestoration) history.scrollRestoration = previousScrollRestoration
  bottomReadObserver?.disconnect()
  olderMessagesObserver?.disconnect()
  olderMessagesScrollRoot = null
  readScrollRoot?.removeEventListener('scroll', scheduleReadVisibilityCheck)
  readScrollRoot = null
  if (readScrollAnimationFrame !== undefined) cancelAnimationFrame(readScrollAnimationFrame)
  stopQueuedAutoSend?.()
  cleanupRunMessages()
})
</script>

<template>
  <UDashboardPanel>
    <template #header>
      <AppNavbar :title="title" :workspace-status="workspaceStatus" />
    </template>

    <template #body>
      <UContainer class="mx-auto w-full max-w-[740px] py-6">
        <div ref="chatContainer">
          <div v-if="isLoadingSession" class="min-h-[calc(100dvh-14rem)] space-y-6 pt-2" aria-label="Loading chat">
          <div
            v-for="index in loadingSkeletonCount"
            :key="index"
            class="flex animate-pulse"
            :class="index % 2 === 0 ? 'justify-end' : 'justify-start'"
          >
            <div
              class="rounded-2xl bg-muted"
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
            <UButton color="neutral" variant="soft" label="Try again" @click="() => refresh()" />
          </div>
        </div>

        <template v-else>
          <div
            v-if="hasOlderMessages || olderMessagesError"
            ref="olderMessagesSentinel"
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
              @click="loadOlderMessages"
            />
            <p v-if="olderMessagesError" class="text-xs text-error">
              {{ olderMessagesError }}
            </p>
          </div>
          <UChatMessages
            :messages="messages"
            :status="chatMessagesStatus"
            :shouldAutoScroll="true"
            :shouldScrollToBottom="true"
            :autoScroll="true"
            class="[--last-message-height:0px]"
          >
            <template #indicator>
              <ChatRunActivityIndicator :label="currentActivityLabel || 'Working…'" />
            </template>

            <template #content="{ message }: { message: WebChatMessage }">
              <ChatMessageContent
                v-model:editing-text="editingText"
                :message="message"
                :copied-message-id="copiedMessageId"
                :editing-message-id="editingMessageId"
                :saving-edited-message-id="savingEditedMessageId"
                :is-running="isRunning"
                :workspace="context.selectedWorkspace.value"
                :latest-change-part-key="latestGitChangePartKey"
                :set-editing-message-container="setEditingMessageContainer"
                @copy="copyMessage"
                @regenerate="regenerateResponse"
                @edit="startEditingMessage"
                @cancel-edit="cancelEditingMessage"
                @save-edit="saveEditedMessage"
                @retry-failed="retryFailedMessage"
                @edit-failed="editFailedMessage"
              />
            </template>
          </UChatMessages>
          <UChatMessage
            v-if="showRunActivityIndicator"
            id="run-activity-indicator"
            role="assistant"
            variant="naked"
            class="px-2.5"
          >
            <template #content>
              <ChatRunActivityIndicator :label="currentActivityLabel || 'Working…'" />
            </template>
          </UChatMessage>
          <div ref="bottomReadSentinel" class="h-px w-full" aria-hidden="true" />
        </template>
        </div>
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
            @paste="onPromptPaste"
            @keydown.down="onPromptArrowDown"
            @keydown.up="onPromptArrowUp"
            @keydown.esc="onPromptEscape"
            @keydown.enter="onPromptAutocompleteEnter"
          >
            <template #footer>
              <ChatPromptFooter
                :submit-status="chatStatus"
                :context-usage="promptContextUsage"
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
