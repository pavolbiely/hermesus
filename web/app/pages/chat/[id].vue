<script setup lang="ts">
import { playNotificationSound, prepareNotificationSound } from '../../utils/notificationSound'
import { recoverActiveRun } from '../../utils/activeRunRecovery'
import { connectRouteRun } from '../../utils/routeRunConnection'
import type { GitFileSelection, SessionDetailResponse, WebChatAttachment, WebChatMessage } from '~/types/web-chat'
import { type QueuedMessage, shouldAutoSendQueuedMessage } from '~/utils/queuedMessages'
import { latestChangePartKey, messageText } from '~/utils/chatMessages'
import { writeClipboardText } from '~/utils/clipboard'
import { mergeOptimisticUserMessages } from '~/utils/optimisticChatMessages'
import { markLocalMessageFailed, markLocalMessageSending, removeLocalMessage } from '~/utils/failedChatMessages'
import { isElementVisibleInRoot, nearestScrollableAncestor, scrollElementTreeToBottomAfterRender } from '~/utils/chatInitialScroll'
import { loadingChatSkeletonCount } from '~/utils/chatLoadingState'
import { latestContextUsageTokens } from '~/utils/contextUsage'
import { readAloudAutoReadResponsesEnabled } from '~/utils/readAloudPreferences'

const INITIAL_SESSION_MESSAGE_LIMIT = 60
const OLDER_SESSION_MESSAGE_LIMIT = 80
const CHAT_PROMPT_MAX_ROWS = 6
const STREAM_AUTO_SCROLL_PAUSE_DISTANCE = 160
const STREAM_AUTO_SCROLL_RESUME_DISTANCE = 80
const STREAM_AUTO_SCROLL_RESUME_EPSILON = 4
const STREAM_AUTO_SCROLL_FOLLOWING_MS = 220

const { route, sessionId } = useChatRouteState()
const api = useHermesApi()
const sessionCache = useWebChatSessionCache(api)
const composer = useChatComposerCapabilities()
const providerUsage = useProviderUsage(
  composer.selectedProvider,
  composer.selectedModel
)
const activeChatRuns = useActiveChatRuns()
const notificationOpenedSessionId = useState<string | null>('chat-notification-opened-session-id', () => null)
const context = useChatComposerContext()
const toast = useToast()
const { read: readMessageAloud, stop: stopReadAloud } = useMessageReadAloud()
const generatingCommitMessage = ref(false)
const generatedCommitMessage = ref('')
const commitMessageModalOpen = ref(false)
const commitMessageCopied = ref(false)
const chatContainer = ref<HTMLElement | null>(null)
const chatFooterContainer = ref<HTMLElement | null>(null)
const chatPromptColumn = ref<HTMLElement | null>(null)
const chatTaskPlanOverlay = ref<HTMLElement | null>(null)
const promptOverlayHeight = ref(0)
const bottomReadSentinel = ref<HTMLElement | null>(null)
const olderMessagesSentinel = ref<HTMLElement | null>(null)
const initialScrollSettledSessionId = ref<string | null>(null)
const lastRenderedMessageCount = ref(0)
const loadingSkeletonCount = computed(() => loadingChatSkeletonCount(lastRenderedMessageCount.value))
const copiedMessageId = ref<string | null>(null)
const workspaceInvalidSignal = ref(0)
const loadingOlderMessages = ref(false)
const olderMessagesError = ref<string | null>(null)
let preserveScrollAfterPrepend: { root: Element, previousScrollHeight: number, previousScrollTop: number } | null = null
let copiedMessageTimer: ReturnType<typeof setTimeout> | undefined
let commitMessageCopiedTimer: ReturnType<typeof setTimeout> | undefined
const refreshSessions = inject<() => Promise<void> | void>('refreshSessions')
const markSessionRead = inject<(sessionId: string, messageCount: number) => void>('markSessionRead')
const requestedSessionId = inject<Readonly<Ref<string | null>>>('requestedSessionId')
let optimisticUserMessageIds = new Set<string>()
let bottomReadObserver: IntersectionObserver | undefined
let olderMessagesObserver: IntersectionObserver | undefined
let olderMessagesScrollRoot: Element | null = null
let readScrollRoot: Element | null = null
let readScrollAnimationFrame: number | undefined
let previousScrollRestoration: ScrollRestoration | undefined
let chatFooterResizeObserver: ResizeObserver | undefined
let streamAutoScrollObserver: MutationObserver | undefined
let streamAutoScrollRoot: Element | null = null
let streamAutoScrollFrame: number | undefined
let streamAutoScrollFollowingTimer: ReturnType<typeof setTimeout> | undefined
let streamAutoScrollPaused = false
let streamAutoScrollFollowing = false
let streamAutoScrollUserOverride = false
let streamAutoScrollLastTouchY: number | undefined

type SendMessageOptions = {
  clearInput?: boolean
  includeCurrentAttachments?: boolean
}

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
const isSwitchingSession = computed(() => Boolean(requestedSessionId?.value && requestedSessionId.value !== sessionId.value))
const isLoadingSession = computed(() => isSwitchingSession.value || ((sessionStatus.value === 'idle' || sessionStatus.value === 'pending') && !displayedData.value))
const hasSession = computed(() => Boolean(displayedData.value?.session))
const currentSessionArchived = computed(() => displayedData.value?.session.archived === true)
const restoringArchivedSession = ref(false)
const restoreNeedsWorkspace = ref(false)
const restoreWorkspace = ref<string>()
const restoreWorkspaceOptions = computed(() => context.workspaces.value.map(workspace => ({
  label: workspace.label || workspace.path,
  value: workspace.path
})))

watch([currentSessionArchived, () => displayedData.value?.session.workspace, context.workspaces], ([archived, workspace]) => {
  if (!archived || !workspace || !context.workspaces.value.length) return
  if (context.workspaces.value.some(item => item.path === workspace)) return
  restoreNeedsWorkspace.value = true
  restoreWorkspace.value ||= context.selectedWorkspace.value || restoreWorkspaceOptions.value[0]?.value
})
const {
  messages,
  submitStatus,
  streamError,
  chatStatus,
  currentActivityLabel,
  currentEta,
  currentEtaExpired,
  currentEtaRemainingMs,
  latestTaskPlan,
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
  activeChatRuns,
  onAssistantCompleted(message) {
    if (readAloudAutoReadResponsesEnabled()) void readMessageAloud(message, { queue: true })
  }
})
const error = computed(() => streamError.value)
const {
  input,
  slashCommands,
  selectSlashCommand,
  onPromptArrowDown,
  onPromptArrowUp,
  onPromptEscape,
  onPromptAutocompleteEnter,
  appendVoiceText,
  attachFiles,
  onPromptPaste,
  isDraggingFiles,
  onPromptDragEnter,
  onPromptDragOver,
  onPromptDragLeave,
  onPromptDrop
} = useChatComposerState({
  sessionId,
  context,
  chatStatus,
  toast,
  showError
})
const latestGitChangePartKey = computed(() => latestChangePartKey(messages.value))
const chatMessagesStatus = computed(() => chatStatus.value === 'submitted' ? 'streaming' : chatStatus.value)
const canAutoSendQueuedMessage = computed(() => shouldAutoSendQueuedMessage({
  hasSession: hasSession.value,
  queuedCount: queuedForSession.value.length,
  isRunning: isRunning.value,
  hasActiveRun: Boolean(displayedData.value?.activeRun),
  isSubmitting: submitStatus.value === 'submitted'
}))
const activeRunAssistantMessageId = computed(() => {
  if (!isRunning.value) return null
  return [...messages.value].reverse().find(message => message.role === 'assistant')?.id ?? null
})
const showRunActivityIndicator = computed(() => Boolean(currentActivityLabel.value))
const promptContextUsage = computed(() => {
  const model = composer.models.value.find(model => model.id === composer.selectedModel.value && (!composer.selectedProvider.value || model.provider === composer.selectedProvider.value))
    || composer.models.value.find(model => model.id === composer.selectedModel.value)
  if (!model?.contextWindowTokens || !model.autoCompressTokens) return null

  const usage = latestContextUsageTokens(messages.value, isRunning.value)
  if (!usage) return null
  return {
    usedTokens: usage.tokens,
    maxTokens: model.contextWindowTokens,
    autoCompressTokens: model.autoCompressTokens,
    compressionCount: Math.max(0, displayedData.value?.compressionCount || 0),
    estimated: usage.estimated
  }
})

function formatPromptEta(ms: number) {
  const totalSeconds = Math.max(0, Math.ceil(ms / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60)
    const remainingMinutes = minutes % 60
    return `${hours}h ${remainingMinutes.toString().padStart(2, '0')}m`
  }
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

const promptEtaLabel = computed(() => {
  if (!currentEta.value) return null
  if (currentEtaExpired.value) return '~updating…'
  if (currentEtaRemainingMs.value === null || currentEtaRemainingMs.value === undefined) return null
  return `${currentEta.value.isApproximate ? '~' : ''}${formatPromptEta(currentEtaRemainingMs.value)}`
})

const promptEtaTooltip = computed(() => {
  const eta = currentEta.value
  if (!eta) return 'Estimated time remaining'
  if (currentEtaExpired.value) return 'Estimate is stale; waiting for update'
  const slices = eta.totalSlices ? `${eta.completedSlices || 0}/${eta.totalSlices} slices` : null
  const source = eta.source === 'task_plan'
    ? 'Based on task plan progress'
    : eta.source === 'explicit_progress'
      ? 'Approximate — inferred from runtime progress'
      : eta.source === 'runtime_fallback'
        ? 'Approximate — inferred from runtime activity'
        : eta.source === 'prompt_fallback'
          ? 'Approximate — no explicit task plan yet'
          : 'Approximate estimate'
  const details = [eta.taskType, eta.projectArea, eta.validationProfile].filter(Boolean).join(' · ')
  return [source, slices, details || eta.basis, eta.confidence].filter(Boolean).join(' · ')
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
  selectedProvider: composer.selectedProvider,
  selectedReasoningEffort: composer.selectedReasoningEffort,
  activeChatRuns,
  connectRun,
  rememberLastUsedSelection: composer.rememberLastUsedSelection,
  rememberSessionSelection: composer.rememberSessionSelection,
  scrollSubmittedMessageToBottom,
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

watch(sessionId, (newSessionId, previousSessionId) => {
  if (previousSessionId && newSessionId !== previousSessionId) stopReadAloud()
  initialScrollSettledSessionId.value = null
})

watch(
  () => [displayedData.value?.session.id, messages.value.length] as const,
  async ([loadedSessionId]) => {
    if (loadedSessionId !== sessionId.value) return
    if (initialScrollSettledSessionId.value === loadedSessionId) return

    await scrollChatToBottom()
    attachReadScrollListener()
    attachOlderMessagesObserver()
    markCurrentSessionReadIfVisible()
    initialScrollSettledSessionId.value = loadedSessionId
  },
  { immediate: true, flush: 'post' }
)

watch(
  () => [notificationOpenedSessionId.value, displayedData.value?.session.id] as const,
  async ([openedSessionId, loadedSessionId]) => {
    if (!openedSessionId || openedSessionId !== sessionId.value || loadedSessionId !== sessionId.value) return

    await scrollChatToBottom()
    markCurrentSessionReadIfVisible()
    activeChatRuns.clearLocalUnread(sessionId.value)
    if (notificationOpenedSessionId.value === openedSessionId) notificationOpenedSessionId.value = null
  },
  { immediate: true, flush: 'post' }
)

watch(
  () => displayedData.value?.session,
  async (session) => {
    if (!session || session.id !== sessionId.value) return

    const targetSessionId = session.id
    composer.initializeForSession(session)
    await context.initializeForSession(session)
    if (targetSessionId !== sessionId.value) return

    composer.applySessionSelection(session)
  },
  { immediate: true }
)

const {
  title,
  workspaceStatus
} = useChatHeaderState({
  displayedData,
  isLoadingSession,
  sessionError,
  hasSession,
  activeChatRuns
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

function showError(err: unknown, fallback: string) {
  const message = getHermesErrorMessage(err, fallback)
  streamError.value = new Error(message)
  toast.add({ color: 'error', title: fallback, description: message })
}

function showVoiceError(message: string) {
  showError(new Error(message), 'Voice input failed')
}

function rememberCurrentSessionSelection() {
  if (displayedData.value?.session.id !== sessionId.value) return
  composer.rememberSessionSelection(sessionId.value)
}

function updateSelectedModel(model: string) {
  composer.selectedModel.value = model
  rememberCurrentSessionSelection()
}

function updateSelectedProvider(provider: string | null) {
  composer.selectedProvider.value = provider
  rememberCurrentSessionSelection()
}

function updateSelectedReasoningEffort(reasoningEffort: string) {
  composer.selectedReasoningEffort.value = reasoningEffort
  rememberCurrentSessionSelection()
}

function rememberSubmittedSelection(submittedSessionId: string | null | undefined = sessionId.value) {
  composer.rememberLastUsedSelection()
  composer.rememberSessionSelection(submittedSessionId)
}

function showCommitMessageCopied() {
  commitMessageCopied.value = true
  if (commitMessageCopiedTimer) clearTimeout(commitMessageCopiedTimer)
  commitMessageCopiedTimer = setTimeout(() => {
    commitMessageCopied.value = false
    commitMessageCopiedTimer = undefined
  }, 2500)
}

async function copyGeneratedCommitMessage() {
  if (!generatedCommitMessage.value) return

  try {
    await writeClipboardText(generatedCommitMessage.value)
    showCommitMessageCopied()
  } catch (err) {
    toast.add({
      color: 'error',
      title: 'Could not copy commit message',
      description: err instanceof Error ? err.message : String(err)
    })
  }
}

async function generateCommitMessage() {
  if (!context.selectedWorkspace.value || generatingCommitMessage.value) return

  generatingCommitMessage.value = true
  generatedCommitMessage.value = ''
  commitMessageCopied.value = false
  if (commitMessageCopiedTimer) {
    clearTimeout(commitMessageCopiedTimer)
    commitMessageCopiedTimer = undefined
  }
  try {
    const status = await api.getGitStatus(context.selectedWorkspace.value)
    const selection: GitFileSelection[] = status.files.map(file => ({ area: file.area, path: file.path }))
    if (!selection.length) {
      toast.add({ color: 'warning', title: 'No Git changes', description: 'There are no changed files to generate a commit message from.' })
      return
    }

    const suggestion = await api.generateCommitMessage({
      workspace: context.selectedWorkspace.value,
      sessionId: sessionId.value,
      selection
    })
    generatedCommitMessage.value = [suggestion.subject, suggestion.body].filter(Boolean).join('\n\n')
    commitMessageModalOpen.value = true
  } catch (err) {
    showError(err, 'Could not generate commit message')
  } finally {
    generatingCommitMessage.value = false
  }
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
  activeChatRuns.clearLocalUnread(sessionId.value)
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

function updateAutoScrollOffset() {
  const footerHeight = chatFooterContainer.value?.getBoundingClientRect().height ?? 0
  const overlayHeight = Math.ceil(chatTaskPlanOverlay.value?.getBoundingClientRect().height ?? 0)
  const columnRect = chatPromptColumn.value?.getBoundingClientRect()

  promptOverlayHeight.value = overlayHeight
  document.documentElement.style.setProperty('--chat-auto-scroll-bottom', `${Math.ceil(footerHeight + overlayHeight + 12)}px`)
  document.documentElement.style.setProperty('--chat-auto-scroll-left', `${Math.ceil(columnRect?.left ?? 0)}px`)
  document.documentElement.style.setProperty('--chat-auto-scroll-width', `${Math.ceil(columnRect?.width ?? window.innerWidth)}px`)
}

function observeChatFooter() {
  chatFooterResizeObserver?.disconnect()
  window.removeEventListener('resize', updateAutoScrollOffset)

  const footer = chatFooterContainer.value
  if (!footer || typeof ResizeObserver !== 'function') {
    updateAutoScrollOffset()
    return
  }

  chatFooterResizeObserver = new ResizeObserver(updateAutoScrollOffset)
  chatFooterResizeObserver.observe(footer)
  if (chatTaskPlanOverlay.value) chatFooterResizeObserver.observe(chatTaskPlanOverlay.value)
  window.addEventListener('resize', updateAutoScrollOffset)
  updateAutoScrollOffset()
}

function waitForAnimationFrame() {
  if (typeof requestAnimationFrame !== 'function') return Promise.resolve()
  return new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
}

async function startRunForLocalMessage(
  userMessage: WebChatMessage,
  text: string,
  clientMessageId: string,
  attachmentIds: string[]
) {
  const targetSessionId = sessionId.value
  try {
    const run = await api.startRun(text, {
      sessionId: targetSessionId,
      model: composer.selectedModel.value,
      provider: composer.selectedProvider.value,
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
    rememberSubmittedSelection(targetSessionId)
    playNotificationSound('sent')
    void refreshSessions?.()
    connectRun(run.runId, targetSessionId)
  } catch (err) {
    const errorMessage = getHermesErrorMessage(err, 'Not sent')
    messages.value = markLocalMessageFailed(messages.value, userMessage.id, errorMessage)
    showError(err, 'Failed to send message')
    submitStatus.value = 'error'
    activeChatRuns.markFinished(sessionId.value)
    throw err
  }
}

function scrollChatToBottom() {
  return scrollElementTreeToBottomAfterRender(chatContainer.value, {
    waitForDomUpdate: nextTick,
    waitForFrame: waitForAnimationFrame,
    frameCount: 2,
    stableFrameCount: 2,
    maxFrameCount: 16
  })
}

function scrollSubmittedMessageToBottom() {
  void scrollChatToBottom()
}

function scrollDistanceFromBottom(root: Element) {
  return Math.max(0, root.scrollHeight - root.clientHeight - root.scrollTop)
}

function updateStreamAutoScrollPaused() {
  if (!streamAutoScrollRoot) return

  const distance = scrollDistanceFromBottom(streamAutoScrollRoot)
  if (distance <= STREAM_AUTO_SCROLL_RESUME_DISTANCE && (!streamAutoScrollUserOverride || distance <= STREAM_AUTO_SCROLL_RESUME_EPSILON)) {
    streamAutoScrollPaused = false
    streamAutoScrollUserOverride = false
    return
  }

  if (streamAutoScrollUserOverride) return

  if (!streamAutoScrollFollowing && distance >= STREAM_AUTO_SCROLL_PAUSE_DISTANCE) {
    streamAutoScrollPaused = true
  }
}

function stopFollowingStreamAutoScroll() {
  streamAutoScrollFollowing = false
}

function markFollowingStreamAutoScroll() {
  streamAutoScrollFollowing = true
  if (streamAutoScrollFollowingTimer) clearTimeout(streamAutoScrollFollowingTimer)
  streamAutoScrollFollowingTimer = setTimeout(stopFollowingStreamAutoScroll, STREAM_AUTO_SCROLL_FOLLOWING_MS)
}

function handleStreamAutoScrollUserInput() {
  streamAutoScrollFollowing = false
  if (streamAutoScrollFollowingTimer) clearTimeout(streamAutoScrollFollowingTimer)
  requestAnimationFrame(updateStreamAutoScrollPaused)
}

function pauseStreamAutoScrollForUser() {
  streamAutoScrollPaused = true
  streamAutoScrollUserOverride = true
  streamAutoScrollFollowing = false
  if (streamAutoScrollFollowingTimer) clearTimeout(streamAutoScrollFollowingTimer)
  if (streamAutoScrollFrame !== undefined) {
    cancelAnimationFrame(streamAutoScrollFrame)
    streamAutoScrollFrame = undefined
  }
  if (streamAutoScrollRoot) {
    streamAutoScrollRoot.scrollTo({ top: streamAutoScrollRoot.scrollTop, behavior: 'auto' })
  }
}

function handleStreamAutoScrollWheel(event: Event) {
  const { deltaY } = event as WheelEvent
  if (deltaY < 0) {
    pauseStreamAutoScrollForUser()
    return
  }

  handleStreamAutoScrollUserInput()
}

function handleStreamAutoScrollTouchStart(event: Event) {
  streamAutoScrollLastTouchY = (event as TouchEvent).touches[0]?.clientY
}

function handleStreamAutoScrollTouchMove(event: Event) {
  const nextY = (event as TouchEvent).touches[0]?.clientY
  if (nextY === undefined || streamAutoScrollLastTouchY === undefined) return

  const deltaY = nextY - streamAutoScrollLastTouchY
  streamAutoScrollLastTouchY = nextY
  if (deltaY > 0) {
    pauseStreamAutoScrollForUser()
    return
  }

  handleStreamAutoScrollUserInput()
}

function attachStreamAutoScrollRoot() {
  const nextRoot = nearestScrollableAncestor(chatContainer.value)
  if (nextRoot === streamAutoScrollRoot) return

  streamAutoScrollRoot?.removeEventListener('scroll', updateStreamAutoScrollPaused)
  streamAutoScrollRoot?.removeEventListener('wheel', handleStreamAutoScrollWheel)
  streamAutoScrollRoot?.removeEventListener('touchstart', handleStreamAutoScrollTouchStart)
  streamAutoScrollRoot?.removeEventListener('touchmove', handleStreamAutoScrollTouchMove)
  streamAutoScrollRoot = nextRoot
  streamAutoScrollPaused = false
  streamAutoScrollUserOverride = false
  streamAutoScrollLastTouchY = undefined
  streamAutoScrollRoot?.addEventListener('scroll', updateStreamAutoScrollPaused, { passive: true })
  streamAutoScrollRoot?.addEventListener('wheel', handleStreamAutoScrollWheel, { passive: true })
  streamAutoScrollRoot?.addEventListener('touchstart', handleStreamAutoScrollTouchStart, { passive: true })
  streamAutoScrollRoot?.addEventListener('touchmove', handleStreamAutoScrollTouchMove, { passive: true })
}

function scheduleStreamAutoScroll() {
  if (!isRunning.value || loadingOlderMessages.value || streamAutoScrollPaused) return
  if (streamAutoScrollFrame !== undefined) return

  streamAutoScrollFrame = requestAnimationFrame(() => {
    streamAutoScrollFrame = undefined
    attachStreamAutoScrollRoot()
    const root = streamAutoScrollRoot
    if (!root || streamAutoScrollPaused) return

    markFollowingStreamAutoScroll()
    root.scrollTop = root.scrollHeight
  })
}

function observeStreamAutoScroll() {
  streamAutoScrollObserver?.disconnect()
  if (!chatContainer.value || typeof MutationObserver !== 'function') return

  attachStreamAutoScrollRoot()
  streamAutoScrollObserver = new MutationObserver(scheduleStreamAutoScroll)
  streamAutoScrollObserver.observe(chatContainer.value, {
    childList: true,
    characterData: true,
    subtree: true
  })
}

async function restoreArchivedSession() {
  const session = displayedData.value?.session
  if (!session || restoringArchivedSession.value) return

  restoringArchivedSession.value = true
  try {
    if (restoreNeedsWorkspace.value && !restoreWorkspace.value) {
      toast.add({ color: 'warning', title: 'Choose a workspace to restore this chat.' })
      return
    }
    const response = await api.setSessionArchived(session.id, false, { workspace: restoreWorkspace.value || undefined })
    data.value = response
    sessionCache.set(response)
    context.selectWorkspace(response.session.workspace)
    restoreNeedsWorkspace.value = false
    restoreWorkspace.value = undefined
    await refreshSessions?.()
    toast.add({ title: 'Chat restored' })
  } catch (err) {
    const message = getHermesErrorMessage(err, 'Failed to restore chat')
    if (message.includes('Choose another workspace')) {
      restoreNeedsWorkspace.value = true
      restoreWorkspace.value ||= context.selectedWorkspace.value || restoreWorkspaceOptions.value[0]?.value
      await context.loadWorkspaces()
      toast.add({ color: 'warning', title: 'Choose a workspace to restore this chat.' })
      return
    }
    showError(err, 'Failed to restore chat')
  } finally {
    restoringArchivedSession.value = false
  }
}

async function sendMessageNow(message: string, options: SendMessageOptions = {}) {
  if (currentSessionArchived.value) {
    toast.add({ color: 'warning', title: 'Restore this chat before sending a message.' })
    return
  }
  const pendingAttachments = options.includeCurrentAttachments === false ? [] : [...context.attachments.value]
  void prepareNotificationSound()
  if (options.clearInput !== false) input.value = ''
  submitStatus.value = 'submitted'
  const clientMessageId = crypto.randomUUID()
  const userMessage = createLocalMessage('user', message)
  userMessage.clientMessageId = clientMessageId
  userMessage.localStatus = 'sending'
  optimisticUserMessageIds.add(userMessage.id)
  if (pendingAttachments.length) userMessage.parts.unshift({ type: 'media', attachments: pendingAttachments })
  messages.value.push(userMessage)
  scrollSubmittedMessageToBottom()
  if (options.includeCurrentAttachments !== false) context.clearAttachments()

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
  if (currentSessionArchived.value) {
    toast.add({ color: 'warning', title: 'Restore this chat before regenerating.' })
    return
  }
  if (message.role !== 'assistant') return
  if (activeChatRuns.isRunning(sessionId.value) || submitStatus.value === 'submitted') return

  const userMessage = previousUserMessage(message)
  const content = userMessage ? messageText(userMessage).trim() : ''
  if (!userMessage || !content) {
    toast.add({ color: 'warning', title: 'Could not find the prompt to regenerate.' })
    return
  }

  const targetSessionId = sessionId.value
  const previousData = data.value || displayedData.value || undefined
  const previousMessages = [...messages.value]
  void prepareNotificationSound()
  submitStatus.value = 'submitted'

  try {
    const updated = await api.editMessage(targetSessionId, userMessage.id, content)
    data.value = updated
    sessionCache.set(updated)
    messages.value = [...updated.messages]

    const run = await api.startRun(content, {
      sessionId: targetSessionId,
      model: composer.selectedModel.value,
      provider: composer.selectedProvider.value,
      reasoningEffort: composer.selectedReasoningEffort.value,
      workspace: context.selectedWorkspace.value,
      attachments: attachmentIdsForMessage(userMessage),
      editedMessageId: userMessage.id
    })
    rememberSubmittedSelection(targetSessionId)
    playNotificationSound('sent')
    void refreshSessions?.()
    connectRun(run.runId, targetSessionId)
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
  if (currentSessionArchived.value) {
    toast.add({ color: 'warning', title: 'Restore this chat before retrying.' })
    return
  }
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
  if (currentSessionArchived.value) {
    toast.add({ color: 'warning', title: 'Restore this chat before editing.' })
    return
  }
  input.value = messageText(message)
  context.attachments.value = attachmentsForMessage(message)
  messages.value = removeLocalMessage(messages.value, message.id)
  optimisticUserMessageIds.delete(message.id)
}

async function onSubmit() {
  if (currentSessionArchived.value) {
    toast.add({ color: 'warning', title: 'Restore this chat before sending a message.' })
    return
  }
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
        await sendMessageNow(queued.text, { clearInput: false, includeCurrentAttachments: false })
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
      await sendMessageNow(priority.text, { clearInput: false, includeCurrentAttachments: false })
    } catch {
      queuedMessages.prepend(priority)
    }
    return
  }

  const queued = queuedMessages.shiftForSession(sessionId.value)
  if (!queued) return

  try {
    await sendMessageNow(queued.text, { clearInput: false, includeCurrentAttachments: false })
  } catch {
    queuedMessages.prepend(queued)
  }
}

watch(
  canAutoSendQueuedMessage,
  (shouldSend) => {
    if (shouldSend) void sendNextQueuedMessage()
  },
  { immediate: true }
)

watch(
  () => displayedData.value?.activeRun,
  (activeRun) => {
    if (activeRun?.sessionId === sessionId.value && activeRun.eta) {
      currentEta.value = activeRun.eta
    }
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
  [chatFooterContainer, chatPromptColumn, chatTaskPlanOverlay],
  () => observeChatFooter(),
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
  observeStreamAutoScroll()
  observeChatFooter()

  stopQueuedAutoSend = activeChatRuns.onFinished(async (finishedSessionId) => {
    if (finishedSessionId !== sessionId.value) return
    await sendNextQueuedMessage()
  })
})

onBeforeUnmount(() => {
  if (copiedMessageTimer) clearTimeout(copiedMessageTimer)
  if (commitMessageCopiedTimer) clearTimeout(commitMessageCopiedTimer)
  if (previousScrollRestoration) history.scrollRestoration = previousScrollRestoration
  bottomReadObserver?.disconnect()
  olderMessagesObserver?.disconnect()
  chatFooterResizeObserver?.disconnect()
  streamAutoScrollObserver?.disconnect()
  streamAutoScrollRoot?.removeEventListener('scroll', updateStreamAutoScrollPaused)
  streamAutoScrollRoot?.removeEventListener('wheel', handleStreamAutoScrollWheel)
  streamAutoScrollRoot?.removeEventListener('touchstart', handleStreamAutoScrollTouchStart)
  streamAutoScrollRoot?.removeEventListener('touchmove', handleStreamAutoScrollTouchMove)
  if (streamAutoScrollFrame !== undefined) cancelAnimationFrame(streamAutoScrollFrame)
  if (streamAutoScrollFollowingTimer) clearTimeout(streamAutoScrollFollowingTimer)
  window.removeEventListener('resize', updateAutoScrollOffset)
  document.documentElement.style.removeProperty('--chat-auto-scroll-bottom')
  document.documentElement.style.removeProperty('--chat-auto-scroll-left')
  document.documentElement.style.removeProperty('--chat-auto-scroll-width')
  olderMessagesScrollRoot = null
  readScrollRoot?.removeEventListener('scroll', scheduleReadVisibilityCheck)
  readScrollRoot = null
  if (readScrollAnimationFrame !== undefined) cancelAnimationFrame(readScrollAnimationFrame)
  stopReadAloud()
  stopQueuedAutoSend?.()
  cleanupRunMessages()
})
</script>

<template>
  <UDashboardPanel>
    <template #header>
      <AppNavbar
        :title="title"
        :workspace-status="workspaceStatus"
        commit-visible
        :commit-disabled="!context.selectedWorkspace.value"
        :commit-loading="generatingCommitMessage"
        @generate-commit="generateCommitMessage"
      />
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
                v-model:editing-text="editingText"
                :message="message"
                :copied-message-id="copiedMessageId"
                :editing-message-id="editingMessageId"
                :saving-edited-message-id="savingEditedMessageId"
                :is-running="isRunning"
                :is-active-run-message="message.id === activeRunAssistantMessageId"
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
          <div ref="bottomReadSentinel" class="h-px w-full" aria-hidden="true" />
        </template>
        </div>
      </UContainer>
    </template>

    <template #footer>
      <div ref="chatFooterContainer">
        <UContainer class="mx-auto w-full max-w-[740px] pb-4 sm:pb-6">
          <div ref="chatPromptColumn" class="bg-transparent">
            <div v-if="sessionError || (!isLoadingSession && !hasSession)" class="flex min-h-36 items-center justify-center">
              <UButton to="/" color="neutral" variant="soft" icon="i-lucide-square-pen" label="Start a new chat" />
            </div>

            <div
              v-else
              class="relative rounded-xl"
              :class="isDraggingFiles ? 'ring-2 ring-primary/40 ring-offset-2 ring-offset-default' : undefined"
              @dragenter="onPromptDragEnter"
              @dragover="onPromptDragOver"
              @dragleave="onPromptDragLeave"
              @drop="onPromptDrop"
            >
              <div
                v-if="latestTaskPlan || queuedForSession.length"
                ref="chatTaskPlanOverlay"
                class="pointer-events-none absolute inset-x-0 bottom-full z-10"
              >
                <ChatPromptOverlay
                  :queued-messages="queuedForSession"
                  :task-plan="latestTaskPlan"
                  :steering-queued-message-id="steeringQueuedMessageId"
                  :disabled="isLoadingSession || !hasSession"
                  @edit-queued-message="editQueuedMessage"
                  @delete-queued-message="deleteQueuedMessage"
                  @steer-queued-message="steerQueuedMessage"
                />
              </div>

              <div
                v-if="currentSessionArchived"
                class="rounded-xl border border-dashed border-default bg-elevated/30 px-4 py-3"
              >
                <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div class="min-w-0">
                    <p class="text-sm font-medium text-highlighted">This chat is archived</p>
                    <p class="text-xs text-muted">
                      {{ restoreNeedsWorkspace ? 'The original workspace no longer exists. Choose where to restore it.' : 'Restore it before sending new messages.' }}
                    </p>
                  </div>
                  <div class="flex min-w-0 items-center gap-2">
                    <USelectMenu
                      v-if="restoreNeedsWorkspace"
                      v-model="restoreWorkspace"
                      :items="restoreWorkspaceOptions"
                      value-key="value"
                      label-key="label"
                      placeholder="Choose workspace"
                      size="sm"
                      class="min-w-52"
                      :loading="context.workspacesLoading.value"
                    />
                    <UButton
                      color="neutral"
                      variant="soft"
                      size="sm"
                      icon="i-lucide-archive-restore"
                      label="Restore"
                      :loading="restoringArchivedSession"
                      @click="restoreArchivedSession"
                    />
                  </div>
                </div>
              </div>

              <UChatPrompt
                v-else
                v-model="input"
                :maxrows="CHAT_PROMPT_MAX_ROWS"
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
                    :submit-disabled="!input.trim()"
                    :context-usage="promptContextUsage"
                    :workspaces="context.workspaces.value"
                    :selected-workspace="context.selectedWorkspace.value"
                    :workspace-invalid-signal="workspaceInvalidSignal"
                    :workspaces-loading="context.workspacesLoading.value"
                    :attachments="context.attachments.value"
                    :attachments-loading="context.attachmentsLoading.value"
                    :models="composer.models.value"
                    :selected-model="composer.selectedModel.value"
                    :selected-provider="composer.selectedProvider.value"
                    :selected-reasoning-effort="composer.selectedReasoningEffort.value"
                    :capabilities-loading="composer.capabilitiesLoading.value"
                    :capabilities-refreshing="composer.capabilitiesRefreshing.value"
                    :capabilities-error="composer.capabilitiesError.value"
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
                    @update-selected-model="updateSelectedModel"
                    @update-selected-provider="updateSelectedProvider"
                    @update-selected-reasoning-effort="updateSelectedReasoningEffort"
                    @refresh-models="composer.refreshCapabilities({ force: true })"
                    @select-slash-command="selectSlashCommand"
                    @highlight-slash-command="slashCommands.highlightedIndex.value = $event"
                  />
                </template>
              </UChatPrompt>
              <div v-if="!currentSessionArchived" class="mt-2 flex items-center gap-3">
                <ProviderUsageBadge
                  display="text"
                  :usage="providerUsage.usage.value"
                  :loading="providerUsage.loading.value"
                />
                <div v-if="promptEtaLabel" class="ml-auto shrink-0">
                  <UTooltip :text="promptEtaTooltip" :content="{ side: 'top', sideOffset: 8, align: 'end' }">
                    <span class="inline-flex items-center gap-1 text-[11px] tabular-nums text-muted">
                      <UIcon name="i-lucide-clock-3" class="size-3" />
                      <span>ETA {{ promptEtaLabel }}</span>
                    </span>
                  </UTooltip>
                </div>
              </div>
              <div
                v-if="isDraggingFiles"
                class="pointer-events-none absolute inset-0 z-20 flex items-center justify-center rounded-xl border border-dashed border-primary/50 bg-primary/10 text-sm font-medium text-highlighted backdrop-blur-sm"
              >
                Drop files to attach
              </div>
            </div>
          </div>
        </UContainer>
      </div>
    </template>
  </UDashboardPanel>

  <UModal
    v-model:open="commitMessageModalOpen"
    title="Generated commit message"
    description="Review the generated message before copying it."
    :ui="{ content: 'sm:max-w-lg' }"
  >
    <template #body>
      <div class="space-y-3">
        <UTextarea
          v-model="generatedCommitMessage"
          readonly
          :rows="14"
          class="w-full font-mono text-sm"
          aria-label="Generated commit message"
        />
      </div>
    </template>

    <template #footer>
      <div class="flex w-full justify-between gap-2">
        <UButton
          color="neutral"
          variant="ghost"
          label="Close"
          @click="commitMessageModalOpen = false"
        />
        <UButton
          color="neutral"
          icon="i-lucide-copy"
          :label="commitMessageCopied ? 'Copied' : 'Copy'"
          @click="copyGeneratedCommitMessage"
        />
      </div>
    </template>
  </UModal>
</template>
