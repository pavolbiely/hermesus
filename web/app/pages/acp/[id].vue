<script setup lang="ts">
import type { PlanEntry } from '@agentclientprotocol/sdk'
import type {
  AvailableCommand,
  AcpListSessionsResponse,
  AcpTranscriptSnapshot,
  PermissionOption,
  RequestPermissionRequest,
  SessionConfigOption,
  SessionModeState,
  SessionModelState
} from '~/types/acp-api'
import type { AcpChatMessage } from '~/types/acp-chat'
import type { ChatPromptAttachment, SlashCommand } from '~/types/chat'
import type { QueuedMessage } from '~/utils/queuedMessages'
import type { ComponentPublicInstance } from 'vue'
import { useScrollShadow } from '@nuxt/ui/composables'
import {
  acpMessageDurationDetails,
  acpMessageText,
  acpMessageTimestampDetails,
  acpTokenDetails,
  formatAcpMessageDuration,
  formatAcpMessageTimestamp,
  formatAcpTokenCount
} from '~/utils/acpMessageMetadata'
import { writeClipboardText } from '~/utils/clipboard'
import { isAcpPlanUpdate, normalizeAcpPlanEntries } from '~/utils/acpPlanNormalization'
import {
  hasThoughtActivity,
  reasoningText,
  runDetailGroups,
  thoughtDetail,
  toolParts,
  type AcpToolPart
} from '~/utils/acpRunDetails'
import { scrollElementTreeToBottom, scrollElementTreeToBottomAfterRender } from '~/utils/chatInitialScroll'
import { acpSidebarSessions } from '~/utils/acpSidebarSessions'
import { shouldAutoSendQueuedMessage } from '~/utils/queuedMessages'
import { toolCallTitle } from '~/utils/toolCalls'

type PendingPermission = {
  appRequestId: string
  request: RequestPermissionRequest
}

type MessageAction = {
  label: string
  icon: string
  kind?: 'default' | 'read-aloud'
  disabled?: boolean
  color?: 'neutral' | 'error'
  variant?: 'ghost'
  onClick: (event: MouseEvent, message: AcpChatMessageWithActions) => void | Promise<void>
}

type AcpChatMessageWithActions = AcpChatMessage & {
  actions?: MessageAction[]
}

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
const input = ref('')
const messagesScrollContainer = ref<HTMLElement | null>(null)
const promptContainer = ref<HTMLElement | null>(null)
const runDetailsElements = new Map<string, HTMLElement>()
const runDetailsScrollCleanup = new Map<string, () => void>()
const { style: messagesScrollShadowStyle } = useScrollShadow(messagesScrollContainer)
const loading = ref(true)
const initialTranscriptScrollPending = ref(true)
const activePromptTurnId = ref<string | null>(null)
const activePromptSessionId = ref<string | null>(null)
const activePromptStartedAt = ref<number | null>(null)
const activePromptClockNow = ref(Date.now())
const pendingPermissions = ref<PendingPermission[]>([])
const editingMessageId = ref<string | null>(null)
const editingText = ref('')
const editingMessageContainer = ref<HTMLElement | null>(null)
const savingEditedMessageId = ref<string | null>(null)
const steeringQueuedMessageId = ref<string | null>(null)
const queuedMessageToSendAfterStop = ref<QueuedMessage | null>(null)
const autoSendingQueuedMessage = ref(false)
const planEntries = ref<PlanEntry[]>([])
const modelState = ref<SessionModelState | null>(null)
const modeState = ref<SessionModeState | null>(null)
const configOptions = ref<SessionConfigOption[]>([])
const availableCommands = ref<AvailableCommand[]>([])
const updatingSessionConfig = ref(false)
const loadingOlderMessages = ref(false)
const hasOlderMessages = ref(false)
const nextTranscriptBefore = ref<number | null>(null)
const error = ref<string | null>(null)
let closeEvents: (() => void) | undefined
let eventSource: EventSource | undefined
let activePromptClockInterval: number | undefined
let sessionLoadSequence = 0
let sessionLoadAbortController: AbortController | undefined
let displayedSessionId: string | null = null
let latestInitialScrollSequence = 0
let latestSubmitScrollSequence = 0

const transcriptPageSize = 80
const stillWorkingDelayMs = 10_000

type ChatSubmitStatus = 'ready' | 'submitted' | 'streaming'

const submitStatusState = ref<ChatSubmitStatus>('ready')
const submitting = computed(() => Boolean(activePromptTurnId.value))
const submitStatus = computed(() => submitting.value ? submitStatusState.value : 'ready')
const queuedForSession = computed(() => queuedMessages.forSession(sessionId.value))
const messages = computed(() => transcript.messages.value)
const currentAcpSession = computed(() => sidebarSessionsData.data.value?.sessions.find(session => session.sessionId === sessionId.value) || null)
const currentSidebarSession = computed(() => acpSidebarSessions(sidebarSessionsData.data.value).find(session => session.id === sessionId.value) || null)
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
const displayMessages = computed<AcpChatMessageWithActions[]>(() => groupProcessMessages(messages.value).map(withNativeMessageActions))
const hoveredAssistantMessageId = ref<string | null>(null)
const focusedAssistantMessageId = ref<string | null>(null)
const chatUserProps = {
  side: 'right' as const,
  variant: 'soft' as const,
  ui: {
    container: 'pb-5',
    actions: 'bottom-0'
  }
}
const chatAssistantProps = {
  side: 'left' as const,
  variant: 'naked' as const
}
const activeRunMessage = computed(() => {
  if (!activePromptTurnId.value) return null
  return [...displayMessages.value].reverse().find(message => (
    message.turnId === activePromptTurnId.value
    && (message.role === 'assistant' || hasRunDetails(message))
  )) || null
})
const currentActivityLabel = computed(() => {
  const activeMessage = activeRunMessage.value
  if (!activePromptTurnId.value) return null
  if (!activeMessage) return fallbackActiveActivityLabel()
  return runActivityLabel(activeMessage) || fallbackActiveActivityLabel()
})
const showRunActivityIndicator = computed(() => Boolean(currentActivityLabel.value))
const currentActivityElapsedLabel = computed(() => {
  const startedAt = activePromptStartedAt.value
  if (!activePromptTurnId.value || !startedAt) return ''
  return formatElapsedDuration(activePromptClockNow.value - startedAt)
})
const selectedModelId = computed({
  get: () => modelState.value?.currentModelId || undefined,
  set: (modelId: string | undefined) => {
    if (modelId) void updateSessionModel(modelId)
  }
})
const selectedModeId = computed({
  get: () => modeState.value?.currentModeId || undefined,
  set: (modeId: string | undefined) => {
    if (modeId) void updateSessionMode(modeId)
  }
})
const modelItems = computed(() => {
  return modelState.value?.availableModels.map(model => ({
    label: model.name,
    value: model.modelId
  })) || []
})
const modeItems = computed(() => {
  return modeState.value?.availableModes.map(mode => ({
    label: mode.name,
    value: mode.id
  })) || []
})
const reasoningConfigOption = computed(() => {
  return configOptions.value.find((option) => {
    if (option.type !== 'select') return false
    const haystack = `${option.category || ''} ${option.id} ${option.name}`.toLowerCase()
    return option.category === 'thought_level' || haystack.includes('reasoning') || haystack.includes('thought')
  }) || null
})
const reasoningItems = computed(() => {
  const option = reasoningConfigOption.value
  return [...(option ? configOptionItems(option) : modeItems.value)].reverse()
})
const workspaceItems = computed(() => context.workspaces.value.map(workspace => ({
  label: workspace.label,
  value: workspace.path
})))
const workspaceLabel = computed(() => {
  const selected = context.selectedWorkspace.value
  if (!selected) return 'Workspace'
  return context.workspaces.value.find(workspace => workspace.path === selected)?.label || selected
})
const selectedModelLabel = computed(() => selectedModelId.value ? modelItems.value.find(item => item.value === selectedModelId.value)?.label : 'Model')
const selectedReasoningId = computed(() => {
  const value = reasoningConfigOption.value?.currentValue ?? selectedModeId.value
  return typeof value === 'string' && value ? value : undefined
})
const selectedModeLabel = computed(() => selectedReasoningId.value ? reasoningItems.value.find(item => item.value === selectedReasoningId.value)?.label : 'Reasoning')
const visibleConfigOptions = computed(() => configOptions.value.filter(option => option.type === 'select' || option.type === 'boolean'))
const hasSessionControls = computed(() => Boolean(modelItems.value.length || modeItems.value.length || visibleConfigOptions.value.length))
const canAutoSendQueuedMessage = computed(() => shouldAutoSendQueuedMessage({
  hasSession: Boolean(sessionId.value && !loading.value),
  queuedCount: queuedForSession.value.length + (queuedMessageToSendAfterStop.value ? 1 : 0),
  isRunning: submitting.value,
  hasActiveRun: Boolean(activePromptTurnId.value),
  isSubmitting: submitStatus.value === 'submitted' || autoSendingQueuedMessage.value
}))
const slashCommandItems = computed<SlashCommand[]>(() => availableCommands.value.map(command => ({
  id: command.name,
  name: `/${command.name}`,
  usage: `/${command.name}${command.input ? ' …' : ''}`,
  description: command.description,
  safety: 'safe'
})))
const slashCommands = useStaticSlashCommands({ input, commands: slashCommandItems })
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

onMounted(async () => {
  await Promise.all([context.initialize(), initializeSession()])
})

onBeforeUnmount(() => {
  abortActiveSessionLoad()
  closeEvents?.()
  stopActivePromptClock()
  runDetailsScrollCleanup.forEach(cleanup => cleanup())
  runDetailsScrollCleanup.clear()
})

watch(sessionId, (newSessionId) => {
  void initializeSession(newSessionId)
})

watch(activePromptTurnId, (turnId, previousTurnId) => {
  if (!turnId) {
    submitStatusState.value = 'ready'
    if (activePromptSessionId.value) {
      activeAcpPrompts.markFinished(activePromptSessionId.value, previousTurnId)
      activePromptSessionId.value = null
    }
    activePromptStartedAt.value = null
    stopActivePromptClock()
    return
  }

  if (submitStatusState.value === 'ready') submitStatusState.value = 'streaming'
  activePromptSessionId.value = sessionId.value
  activeAcpPrompts.markRunning(sessionId.value, turnId)
  activePromptStartedAt.value = activeTurnCreatedAtMs(turnId) ?? Date.now()
  startActivePromptClock()
})

watch(canAutoSendQueuedMessage, (shouldSend) => {
  if (shouldSend) void sendNextQueuedMessage()
}, { immediate: true })

async function initializeSession(targetSessionId = sessionId.value) {
  if (!targetSessionId) return

  abortActiveSessionLoad()
  closeEvents?.()
  closeEvents = undefined
  eventSource = undefined

  const loadSequence = ++sessionLoadSequence
  const abortController = new AbortController()
  sessionLoadAbortController = abortController
  displayedSessionId = targetSessionId

  loading.value = true
  initialTranscriptScrollPending.value = true
  error.value = null
  resetSessionView()

  try {
    const stored = await api.readTranscript(
      targetSessionId,
      { limit: transcriptPageSize },
      { signal: abortController.signal }
    )
    if (!isCurrentSessionLoad(loadSequence, targetSessionId, abortController)) return

    const projectedTranscript = stored.transcript
    const initializedFromProjection = Boolean(projectedTranscript)
    if (projectedTranscript) {
      applyTranscriptSnapshot(projectedTranscript)
      hasOlderMessages.value = stored.hasMore
      nextTranscriptBefore.value = stored.nextBefore
      loading.value = false
      scrollInitialTranscriptToBottom(loadSequence, targetSessionId)
    }

    if (initializedFromProjection) {
      subscribeToSessionEvents(targetSessionId)
      await processQueuedPrompt(targetSessionId)
      return
    }

    const loaded = await api.loadSession(targetSessionId, { signal: abortController.signal })
    if (!isCurrentSessionLoad(loadSequence, targetSessionId, abortController)) return

    modelState.value = loaded.models || modelState.value
    modeState.value = loaded.modes || modeState.value
    configOptions.value = loaded.configOptions || configOptions.value
    loaded.events.forEach(handleBridgeEvent)
    scrollInitialTranscriptToBottom(loadSequence, targetSessionId)

    subscribeToSessionEvents(targetSessionId)
    await processQueuedPrompt(targetSessionId)
  } catch (err) {
    if (isAbortError(err)) return
    if (!isCurrentSessionLoad(loadSequence, targetSessionId, abortController)) return
    showError(err, 'Could not load ACP session')
  } finally {
    if (sessionLoadAbortController === abortController) sessionLoadAbortController = undefined
    if (isCurrentSessionLoad(loadSequence, targetSessionId, abortController)) {
      loading.value = false
    }
  }
}

function subscribeToSessionEvents(targetSessionId: string) {
  const replayOptions = transcript.state.value.cursor === undefined
    ? { replay: false }
    : { afterSequence: transcript.state.value.cursor }
  eventSource = api.subscribeSession(targetSessionId, handleBridgeEvent, () => {
    if (targetSessionId === sessionId.value) error.value ||= 'ACP event stream disconnected.'
  }, replayOptions)
  closeEvents = () => eventSource?.close()
}

async function processQueuedPrompt(targetSessionId: string) {
  const queuedPrompt = pendingAcpPrompts.value[targetSessionId]
  if (queuedPrompt) {
    delete pendingAcpPrompts.value[targetSessionId]
    await router.replace({ path: route.path, query: {} })
    await sendPrompt(queuedPrompt.message, queuedPrompt.attachments)
    return
  }

  const queuedPromptText = typeof route.query.prompt === 'string' ? route.query.prompt : ''
  if (queuedPromptText.trim()) {
    await router.replace({ path: route.path, query: {} })
    await sendPrompt(queuedPromptText)
  }
}

async function onSubmit() {
  const message = input.value.trim()
  if (!message && !context.attachments.value.length) return

  if (submitting.value) {
    enqueueMessage(message)
    return
  }

  const attachments = context.attachments.value
  input.value = ''
  context.clearAttachments()
  await sendPrompt(message, attachments)
}

function warnAttachmentsCannotBeQueued() {
  toast.add({
    color: 'warning',
    title: 'Attachments cannot be queued yet',
    description: 'Wait for the current response to finish, then send the message with attachments.'
  })
}

function enqueueMessage(message: string) {
  if (!message.trim()) return
  if (context.attachments.value.length) {
    warnAttachmentsCannotBeQueued()
    return
  }

  const queued = queuedMessages.enqueue(sessionId.value, message)
  if (queued) input.value = ''
}

function editQueuedMessage(id: string) {
  const queued = queuedForSession.value.find(message => message.id === id)
  if (!queued) return
  input.value = queued.text
  queuedMessages.remove(id)
  void nextTick(() => promptContainer.value?.querySelector('textarea')?.focus())
}

function deleteQueuedMessage(id: string) {
  queuedMessages.remove(id)
}

async function steerQueuedMessage(id: string) {
  const queued = queuedForSession.value.find(message => message.id === id)
  if (!queued) return

  if (!submitting.value) {
    queuedMessages.remove(id)
    const sent = await sendPrompt(queued.text)
    if (!sent) queuedMessages.prepend(queued)
    return
  }

  steeringQueuedMessageId.value = id
  try {
    await api.cancel(sessionId.value)
    queuedMessageToSendAfterStop.value = queued
    queuedMessages.remove(id)
    activeAcpPrompts.markFinished(sessionId.value, activePromptTurnId.value)
    activePromptTurnId.value = null
    toast.add({
      color: 'neutral',
      title: 'Steering after interrupt',
      description: 'Hermes will continue with this message after the current run stops.'
    })
  } catch (err) {
    showError(err, 'Failed to steer run')
  } finally {
    steeringQueuedMessageId.value = null
  }
}

async function sendNextQueuedMessage() {
  if (autoSendingQueuedMessage.value || loading.value || submitting.value) return

  const priority = queuedMessageToSendAfterStop.value?.sessionId === sessionId.value
    ? queuedMessageToSendAfterStop.value
    : null
  const queued = priority || queuedMessages.shiftForSession(sessionId.value)
  if (!queued) return
  if (priority) queuedMessageToSendAfterStop.value = null

  autoSendingQueuedMessage.value = true
  try {
    const sent = await sendPrompt(queued.text)
    if (!sent) queuedMessages.prepend(queued)
  } finally {
    autoSendingQueuedMessage.value = false
  }
}

function abortActiveSessionLoad() {
  sessionLoadAbortController?.abort()
  sessionLoadAbortController = undefined
  latestInitialScrollSequence++
  latestSubmitScrollSequence++
}

function isCurrentSessionLoad(loadSequence: number, targetSessionId: string, abortController: AbortController) {
  return !abortController.signal.aborted
    && loadSequence === sessionLoadSequence
    && targetSessionId === sessionId.value
}

function isAbortError(err: unknown) {
  return (typeof DOMException !== 'undefined' && err instanceof DOMException && err.name === 'AbortError')
    || (err instanceof Error && err.name === 'AbortError')
}

function touchSidebarSession(targetSessionId: string, updatedAt = new Date().toISOString()) {
  const sidebarSessions = sidebarSessionsData.data.value?.sessions
  if (!sidebarSessions?.length) return

  let changed = false
  const sessions = sidebarSessions.map((session) => {
    if (session.sessionId !== targetSessionId) return session
    changed = true
    return { ...session, appUpdatedAt: updatedAt }
  })

  if (changed && sidebarSessionsData.data.value) {
    sidebarSessionsData.data.value = { ...sidebarSessionsData.data.value, sessions }
  }
}

async function sendPrompt(message: string, attachments: ChatPromptAttachment[] = []) {
  error.value = null
  const turnId = crypto.randomUUID()
  const messageId = crypto.randomUUID()
  const occurredAt = new Date().toISOString()
  transcript.applyEvent({
    type: 'user.message',
    eventId: `optimistic-user:${turnId}`,
    sessionId: sessionId.value,
    turnId,
    messageId,
    text: message,
    occurredAt
  })
  touchSidebarSession(sessionId.value, occurredAt)
  activePromptTurnId.value = turnId
  submitStatusState.value = 'submitted'
  scrollSubmittedMessageToBottom(turnId)
  promoteSubmittedStatusToStreaming(turnId)

  try {
    await api.startPrompt(sessionId.value, {
      prompt: attachmentsToPromptBlocks(message || 'See attached files.', attachments),
      turnId,
      messageId
    })
    return true
  } catch (err) {
    if (activePromptTurnId.value === turnId) activePromptTurnId.value = null
    activeAcpPrompts.markFinished(sessionId.value, turnId)
    showError(err, 'Failed to send prompt')
    return false
  }
}

async function stopPrompt() {
  if (!submitting.value) return
  try {
    await api.cancel(sessionId.value)
  } catch (err) {
    showError(err, 'Failed to cancel prompt')
  } finally {
    activeAcpPrompts.markFinished(sessionId.value, activePromptTurnId.value)
    activePromptTurnId.value = null
  }
}

function scrollInitialTranscriptToBottom(loadSequence: number, targetSessionId: string) {
  if (!import.meta.client) return

  const scrollSequence = ++latestInitialScrollSequence
  const isCurrentLoad = () => (
    scrollSequence === latestInitialScrollSequence
    && loadSequence === sessionLoadSequence
    && targetSessionId === sessionId.value
  )

  void (async () => {
    await nextTick()
    if (!isCurrentLoad()) return

    scrollElementTreeToBottom(messagesScrollContainer.value)

    await scrollElementTreeToBottomAfterRender(messagesScrollContainer.value, {
      waitForFrame: waitForAnimationFrame,
      stableFrameCount: 2,
      maxFrameCount: 10
    })

    if (isCurrentLoad()) initialTranscriptScrollPending.value = false
  })()
}

function waitForAnimationFrame() {
  return new Promise<void>((resolve) => {
    requestAnimationFrame(() => resolve())
  })
}

function promoteSubmittedStatusToStreaming(turnId: string) {
  if (!import.meta.client) {
    if (activePromptTurnId.value === turnId && submitStatusState.value === 'submitted') {
      submitStatusState.value = 'streaming'
    }
    return
  }

  requestAnimationFrame(() => {
    if (activePromptTurnId.value === turnId && submitStatusState.value === 'submitted') {
      submitStatusState.value = 'streaming'
    }
  })
}

function scrollSubmittedMessageToBottom(turnId: string) {
  if (!import.meta.client) return

  const scrollSequence = ++latestSubmitScrollSequence
  const isCurrentSubmit = () => (
    scrollSequence === latestSubmitScrollSequence
    && activePromptTurnId.value === turnId
    && targetIsCurrentSession(displayedSessionId)
  )

  void (async () => {
    await nextTick()
    if (!isCurrentSubmit()) return

    scrollElementTreeToBottom(messagesScrollContainer.value)
    await scrollElementTreeToBottomAfterRender(messagesScrollContainer.value, {
      waitForFrame: waitForAnimationFrame,
      stableFrameCount: 2,
      maxFrameCount: 8
    })
  })()
}

function targetIsCurrentSession(targetSessionId: string | null) {
  return Boolean(targetSessionId && targetSessionId === sessionId.value)
}

function startActivePromptClock() {
  activePromptClockNow.value = Date.now()
  if (!import.meta.client || activePromptClockInterval) return
  activePromptClockInterval = window.setInterval(() => {
    activePromptClockNow.value = Date.now()
  }, 1_000)
}

function stopActivePromptClock() {
  if (!activePromptClockInterval) return
  window.clearInterval(activePromptClockInterval)
  activePromptClockInterval = undefined
}

function activeTurnCreatedAtMs(turnId: string) {
  const createdAt = messages.value.find(message => message.turnId === turnId)?.createdAt
  if (!createdAt) return null

  const time = Date.parse(createdAt)
  return Number.isFinite(time) ? time : null
}

function fallbackActiveActivityLabel() {
  const startedAt = activePromptStartedAt.value
  if (!startedAt) return 'Working…'
  return activePromptClockNow.value - startedAt >= stillWorkingDelayMs ? 'Still working…' : 'Working…'
}

function formatElapsedDuration(milliseconds: number) {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1_000))
  if (totalSeconds < 60) return `${totalSeconds}s`

  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`
}

function resetSessionView() {
  initialTranscriptScrollPending.value = true
  transcript.reset()
  pendingPermissions.value = []
  planEntries.value = []
  modelState.value = null
  modeState.value = null
  configOptions.value = []
  availableCommands.value = []
  loadingOlderMessages.value = false
  hasOlderMessages.value = false
  nextTranscriptBefore.value = null
  activePromptTurnId.value = null
  submitStatusState.value = 'ready'
}

function applyTranscriptSnapshot(snapshot: AcpTranscriptSnapshot) {
  transcript.loadSnapshot(snapshot)
  pendingPermissions.value = snapshot.pendingPermissions
  planEntries.value = snapshot.planEntries
  modelState.value = snapshot.models
  modeState.value = snapshot.modes
  configOptions.value = snapshot.configOptions
  availableCommands.value = snapshot.availableCommands
  activePromptTurnId.value = snapshot.prompt?.status === 'running' ? snapshot.prompt.turnId || null : null
  submitStatusState.value = activePromptTurnId.value ? 'streaming' : 'ready'
}

async function loadOlderMessages() {
  if (loadingOlderMessages.value || !hasOlderMessages.value || nextTranscriptBefore.value === null) return
  const container = messagesScrollContainer.value
  const previousScrollHeight = container?.scrollHeight ?? 0
  const previousScrollTop = container?.scrollTop ?? 0

  loadingOlderMessages.value = true
  try {
    const response = await api.readTranscript(sessionId.value, {
      limit: transcriptPageSize,
      before: nextTranscriptBefore.value
    })
    if (response.transcript) transcript.prependMessages(response.transcript.messages)
    hasOlderMessages.value = response.hasMore
    nextTranscriptBefore.value = response.nextBefore
    await nextTick()
    if (container) {
      container.scrollTop = container.scrollHeight - previousScrollHeight + previousScrollTop
    }
  } catch (err) {
    showError(err, 'Failed to load older messages')
  } finally {
    loadingOlderMessages.value = false
  }
}

function handleBridgeEvent(event: Parameters<typeof transcript.applyBridgeEvent>[0]) {
  if (event.sessionId !== sessionId.value) return
  touchSidebarSession(event.sessionId)
  transcript.applyBridgeEvent(event)
  if (event.type === 'permission.requested') {
    pendingPermissions.value = [
      ...pendingPermissions.value.filter(item => item.appRequestId !== event.appRequestId),
      { appRequestId: event.appRequestId, request: event.request }
    ]
  }
  if (event.type === 'permission.resolved') {
    pendingPermissions.value = pendingPermissions.value.filter(item => item.appRequestId !== event.appRequestId)
  }
  if (event.type === 'session.update') {
    const update = event.notification.update
    if (update.sessionUpdate === 'current_mode_update' && modeState.value) {
      modeState.value = { ...modeState.value, currentModeId: update.currentModeId }
    }
    if (update.sessionUpdate === 'config_option_update') {
      configOptions.value = update.configOptions
    }
    if (update.sessionUpdate === 'available_commands_update') {
      availableCommands.value = update.availableCommands
    }
    if (isAcpPlanUpdate(update)) {
      planEntries.value = normalizeAcpPlanEntries(update.entries)
    }
  }
  if (
    event.type === 'prompt.completed'
    || event.type === 'prompt.failed'
    || event.type === 'prompt.cancelled'
  ) {
    if (!('turnId' in event) || event.turnId === activePromptTurnId.value) {
      activeAcpPrompts.markFinished(event.sessionId, 'turnId' in event ? event.turnId : null)
      activePromptTurnId.value = null
    }
  }
}

function showError(err: unknown, fallback: string) {
  const message = err instanceof Error ? err.message : String(err || fallback)
  error.value = message
  toast.add({ color: 'error', title: fallback, description: message })
}

async function respondToPermission(appRequestId: string, option?: PermissionOption) {
  try {
    await api.respondToPermission(appRequestId, option ? { optionId: option.optionId } : { cancelled: true })
  } catch (err) {
    showError(err, 'Failed to respond to permission request')
  }
}

function partText(message: AcpChatMessage) {
  return message.parts.filter(part => part.type === 'text').map(part => part.text).join('')
}

function setRunDetailsElement(messageId: string, element: Element | ComponentPublicInstance | null) {
  let root: HTMLElement | null = null
  if (element instanceof HTMLElement) {
    root = element
  } else if (isComponentWithHtmlRoot(element)) {
    root = element.$el
  }

  if (root) {
    runDetailsElements.set(messageId, root)
  } else {
    runDetailsElements.delete(messageId)
  }
}

function isComponentWithHtmlRoot(value: Element | ComponentPublicInstance | null): value is ComponentPublicInstance & { $el: HTMLElement } {
  return Boolean(value && typeof value === 'object' && '$el' in value && value.$el instanceof HTMLElement)
}

function onRunDetailsOpen(open: boolean, messageId: string) {
  runDetailsScrollCleanup.get(messageId)?.()
  runDetailsScrollCleanup.delete(messageId)
  if (!open) return
  void scrollRunDetailsExpansionIntoView(messageId)
}

async function scrollRunDetailsExpansionIntoView(messageId: string) {
  await nextTick()

  const container = messagesScrollContainer.value
  const element = runDetailsElements.get(messageId)
  if (!container || !element) return

  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const scrollIfNeeded = () => {
    const containerRect = container.getBoundingClientRect()
    const elementRect = element.getBoundingClientRect()
    const bottomGap = 12
    const overflow = elementRect.bottom - containerRect.bottom + bottomGap
    if (overflow <= 0) return

    container.scrollTo({
      top: container.scrollTop + overflow,
      behavior: prefersReducedMotion ? 'auto' : 'smooth'
    })
  }

  let frame = requestAnimationFrame(scrollIfNeeded)
  const observer = new ResizeObserver(() => {
    cancelAnimationFrame(frame)
    frame = requestAnimationFrame(scrollIfNeeded)
  })
  observer.observe(element)

  const timers = [120, 260, 420].map(delay => window.setTimeout(scrollIfNeeded, delay))
  const cleanup = () => {
    observer.disconnect()
    cancelAnimationFrame(frame)
    timers.forEach(timer => window.clearTimeout(timer))
  }
  runDetailsScrollCleanup.set(messageId, cleanup)
  window.setTimeout(() => {
    cleanup()
    if (runDetailsScrollCleanup.get(messageId) === cleanup) {
      runDetailsScrollCleanup.delete(messageId)
    }
  }, 500)
}

function withNativeMessageActions(message: AcpChatMessage): AcpChatMessageWithActions {
  const text = acpMessageText(message).trim()
  if (
    message.role !== 'user'
    || !text
    || message.turnId === activePromptTurnId.value
    || editingMessageId.value === message.id
  ) return message

  return {
    ...message,
    actions: [
      {
        label: 'Copy message',
        icon: 'i-lucide-copy',
        onClick: () => copyMessageText(message)
      },
      {
        label: 'Edit message',
        icon: 'i-lucide-pencil',
        disabled: submitting.value,
        onClick: () => startEditingUserMessage(message)
      }
    ]
  }
}

function assistantMessageActions(message: AcpChatMessage): MessageAction[] {
  const text = acpMessageText(message).trim()
  if (message.role !== 'assistant' || !text || message.turnId === activePromptTurnId.value) return []

  const isSpeaking = readAloud.speakingMessageId.value === message.id
  const isGeneratingSpeech = readAloud.generatingMessageId.value === message.id
  const isReadAloudActive = isSpeaking || isGeneratingSpeech
  return [
    {
      label: 'Regenerate response',
      icon: 'i-lucide-refresh-cw',
      disabled: submitting.value,
      onClick: () => regenerateResponse(message)
    },
    {
      label: 'Copy message',
      icon: 'i-lucide-copy',
      onClick: () => copyMessageText(message)
    },
    {
      label: isReadAloudActive ? 'Stop read aloud' : 'Read aloud',
      icon: isGeneratingSpeech ? 'i-lucide-loader-circle' : isSpeaking ? 'i-lucide-square' : 'i-lucide-volume-2',
      kind: 'read-aloud',
      disabled: !readAloud.isSupported.value,
      color: 'neutral',
      variant: 'ghost',
      onClick: () => readAloud.read(message)
    }
  ]
}

function isReadingAloud(message: AcpChatMessage) {
  return readAloud.speakingMessageId.value === message.id
}

function isGeneratingAloud(message: AcpChatMessage) {
  return readAloud.generatingMessageId.value === message.id
}

function readAloudStatusDetail(message: AcpChatMessage) {
  if (isGeneratingAloud(message)) return 'Generating speech audio'
  if (isReadingAloud(message)) return 'Reading aloud'
  return ''
}

function setAssistantMessageHover(messageId: string, hovered: boolean) {
  if (hovered) {
    hoveredAssistantMessageId.value = messageId
    return
  }
  if (hoveredAssistantMessageId.value === messageId) hoveredAssistantMessageId.value = null
}

function onAssistantMessagePointerLeave(event: PointerEvent, messageId: string) {
  setAssistantMessageHover(messageId, false)

  const container = event.currentTarget
  if (!(container instanceof HTMLElement)) return

  const activeElement = document.activeElement
  if (activeElement instanceof HTMLElement && container.contains(activeElement)) {
    activeElement.blur()
  }
}

function onAssistantMessageFocusOut(event: FocusEvent, messageId: string) {
  const container = event.currentTarget
  const nextFocusTarget = event.relatedTarget
  if (
    container instanceof HTMLElement
    && nextFocusTarget instanceof Node
    && container.contains(nextFocusTarget)
  ) return

  if (focusedAssistantMessageId.value === messageId) focusedAssistantMessageId.value = null
}

function isAssistantFooterVisible(message: AcpChatMessage) {
  return Boolean(
    readAloudStatusDetail(message)
    || hoveredAssistantMessageId.value === message.id
    || focusedAssistantMessageId.value === message.id
  )
}

function hasAssistantFooter(message: AcpChatMessage) {
  return messageMetadataItems(message).length > 0 || assistantMessageActions(message).length > 0
}

function messageMetadataItems(message: AcpChatMessage) {
  if (!acpMessageText(message).trim()) return []

  const items: Array<{ key: string, label: string, title?: string }> = []
  if (message.createdAt) {
    items.push({
      key: 'time',
      label: formatAcpMessageTimestamp(message.createdAt),
      title: acpMessageTimestampDetails(message.createdAt)
    })
  }

  if (message.role === 'user') return items

  if (message.role !== 'assistant' || message.turnId === activePromptTurnId.value) return []

  const duration = formatAcpMessageDuration(message)
  if (duration) {
    items.push({
      key: 'duration',
      label: duration,
      title: acpMessageDurationDetails(message).map(item => `${item.label}: ${item.value}`).join('\n')
    })
  }

  const tokens = formatAcpTokenCount(message)
  if (tokens) {
    items.push({
      key: 'tokens',
      label: tokens,
      title: acpTokenDetails(message.usage).map(item => `${item.label}: ${item.value}`).join('\n')
    })
  }

  return items
}

async function regenerateResponse(message: AcpChatMessage) {
  if (submitting.value) return
  const prompt = previousUserPromptFor(message)
  if (!prompt) {
    toast.add({ color: 'warning', title: 'Could not find the prompt to regenerate.' })
    return
  }
  await sendPrompt(prompt)
}

function previousUserPromptFor(message: AcpChatMessage) {
  const source = messages.value
  const messageIds = new Set(message.id.split(':'))
  let index = source.findIndex(item => messageIds.has(item.id))
  if (index === -1 && message.turnId) {
    index = source.findIndex(item => item.role === 'assistant' && item.turnId === message.turnId && hasTextParts(item))
  }
  if (index === -1) return ''

  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    const candidate = source[cursor]
    if (candidate?.role !== 'user') continue
    const text = acpMessageText(candidate).trim()
    if (text) return text
  }
  return ''
}

async function copyMessageText(message: AcpChatMessage) {
  const text = acpMessageText(message).trim()
  if (!text) return

  try {
    await writeClipboardText(text)
    toast.add({ title: 'Message copied' })
  } catch (err) {
    showError(err, 'Failed to copy message')
  }
}

function setEditingMessageContainer(el: unknown) {
  editingMessageContainer.value = el instanceof HTMLElement ? el : null
}

function cancelEditingUserMessage() {
  editingMessageId.value = null
  editingText.value = ''
  editingMessageContainer.value = null
}

async function focusEditingTextarea() {
  await nextTick()
  const textarea = editingMessageContainer.value?.querySelector('textarea')
  if (!textarea) return
  textarea.focus()
  textarea.setSelectionRange(textarea.value.length, textarea.value.length)
}

async function startEditingUserMessage(message: AcpChatMessage) {
  const text = acpMessageText(message).trim()
  if (!text || submitting.value) return

  editingMessageId.value = message.id
  editingText.value = text
  await focusEditingTextarea()
}

async function saveEditedUserMessage(message: AcpChatMessage) {
  const text = editingText.value.trim()
  if (!text || submitting.value || savingEditedMessageId.value) return

  const previousText = acpMessageText(message).trim()
  if (text === previousText) {
    cancelEditingUserMessage()
    return
  }

  savingEditedMessageId.value = message.id
  try {
    cancelEditingUserMessage()
    await sendPrompt(text)
  } finally {
    savingEditedMessageId.value = null
  }
}

function groupProcessMessages(source: AcpChatMessage[]): AcpChatMessage[] {
  const grouped: AcpChatMessage[] = []

  for (const message of source) {
    const clone = cloneChatMessage(message)
    const previous = grouped[grouped.length - 1]
    if (previous && shouldMergeAssistantProcessMessage(previous, clone)) {
      previous.parts.push(...clone.parts)
      previous.id = `${previous.id}:${clone.id}`
      continue
    }
    grouped.push(clone)
  }

  return grouped
}

function shouldMergeAssistantProcessMessage(previous: AcpChatMessage, next: AcpChatMessage) {
  if (previous.role !== 'assistant' || next.role !== 'assistant') return false
  if (hasTextParts(previous) || hasTextParts(next)) return false
  return hasProcessParts(previous) && hasProcessParts(next)
}

function cloneChatMessage(message: AcpChatMessage): AcpChatMessage {
  return {
    ...message,
    parts: message.parts.map(part => ({ ...part }))
  }
}

function hasTextParts(message: AcpChatMessage) {
  return message.parts.some(part => part.type === 'text' && part.text.trim())
}

function hasProcessParts(message: AcpChatMessage) {
  return message.parts.some(part => part.type === 'tool' || part.type === 'reasoning' || part.type === 'event') || hasThoughtActivity(message)
}

function runDetailSummary(message: AcpChatMessage) {
  const tools = toolParts(message)
  const failed = tools.filter(part => part.error || part.status === 'failed').length
  const running = runningToolParts(message).length
  const counts = tools.reduce<Record<string, number>>((acc, part) => {
    const kind = classifyToolPart(part)
    acc[kind] = (acc[kind] || 0) + 1
    return acc
  }, {})
  const labels: string[] = []

  if (hasThoughtActivity(message)) labels.push('Reasoned')
  if (counts.read) labels.push(`read ${plural(counts.read, 'file')}`)
  if (counts.edit) labels.push(`edited ${plural(counts.edit, 'file')}`)
  if (counts.command) labels.push(`ran ${plural(counts.command, 'command')}`)
  if (counts.browser) labels.push(plural(counts.browser, 'browser action'))
  if (counts.api) labels.push(plural(counts.api, 'API call'))

  const known = ['read', 'edit', 'command', 'browser', 'api'].reduce((sum, key) => sum + (counts[key] || 0), 0)
  const other = tools.length - known
  if (!labels.length && tools.length) labels.push(plural(tools.length, 'action'))
  else if (other > 0) labels.push(plural(other, 'other action'))

  if (failed) labels.push(`${failed} failed`)
  else if (running) labels.push(`${running} running`)
  else if (tools.length) labels.push('completed')

  return labels.join(' · ')
}

function classifyToolPart(part: AcpToolPart) {
  const value = `${part.name || ''} ${part.kind || ''}`.toLowerCase()
  if (value.includes('read') || value.includes('search')) return 'read'
  if (value.includes('patch') || value.includes('write') || value.includes('edit')) return 'edit'
  if (value.includes('terminal') || value.includes('process') || value.includes('command')) return 'command'
  if (value.includes('browser')) return 'browser'
  if (value.includes('mcp') || value.includes('api') || value.includes('supabase') || value.includes('redis')) return 'api'
  return 'other'
}

function plural(count: number, singular: string, pluralValue = `${singular}s`) {
  return `${count} ${count === 1 ? singular : pluralValue}`
}

function runningToolParts(message: AcpChatMessage) {
  return toolParts(message).filter(part => part.state !== 'completed' && !part.error)
}

function runActivityLabel(message: AcpChatMessage) {
  const runningTool = runningToolParts(message)[0]
  if (runningTool) return `Running ${toolCallTitle(runningTool)}`
  if (message.turnId && message.turnId === activePromptTurnId.value && reasoningText(message).trim()) return 'Thinking'
  if (message.role === 'assistant' && hasTextParts(message)) return 'Responding…'
  return ''
}

function hasRunDetails(message: AcpChatMessage) {
  return toolParts(message).length > 0 || hasThoughtActivity(message)
}

function isActiveRunDetailMessage(message: AcpChatMessage) {
  return Boolean(activePromptTurnId.value && message.turnId === activePromptTurnId.value)
}

function shouldRenderRunDetailsBeforeMessage(message: AcpChatMessage) {
  return isActiveRunDetailMessage(message) && hasRunDetails(message)
}

function shouldDefaultOpenThought(message: AcpChatMessage, groupIndex: number) {
  return isActiveRunDetailMessage(message) && groupIndex === runDetailGroups(message).length - 1
}

function runDetailsSpacingClass(message: AcpChatMessage, position: 'before' | 'after') {
  if (position === 'before') return partText(message) ? 'mb-4' : 'mb-2'
  return hasAssistantFooter(message) || partText(message) ? 'mt-4' : 'mt-2'
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

function permissionTitle(permission: PendingPermission) {
  const toolCall = permission.request.toolCall as Record<string, unknown>
  const value = toolCall.title ?? toolCall.name ?? toolCall.kind ?? toolCall.toolCallId
  return typeof value === 'string' && value ? value : 'Permission required'
}

function configOptionItems(option: SessionConfigOption) {
  if (option.type !== 'select') return []
  return option.options.flatMap((item) => {
    if ('options' in item) {
      return item.options
        .filter(child => isSupportedReasoningOption(option, child.value))
        .map(child => ({ label: `${item.name}: ${child.name}`, value: child.value }))
    }
    return isSupportedReasoningOption(option, item.value) ? [{ label: item.name, value: item.value }] : []
  })
}

function isSupportedReasoningOption(option: SessionConfigOption, value: string) {
  if (option.id !== 'reasoning_effort') return true
  return value !== 'none' && value !== 'minimal'
}

async function updateSessionMode(modeId: string) {
  const option = reasoningConfigOption.value
  if (option) {
    await updateConfigOption(option, modeId)
    return
  }
  if (modeId === modeState.value?.currentModeId) return
  updatingSessionConfig.value = true
  try {
    await api.setSessionMode(sessionId.value, modeId)
    if (modeState.value) modeState.value = { ...modeState.value, currentModeId: modeId }
  } catch (err) {
    showError(err, 'Failed to update ACP mode')
  } finally {
    updatingSessionConfig.value = false
  }
}

async function updateSessionModel(modelId: string) {
  if (modelId === modelState.value?.currentModelId) return
  updatingSessionConfig.value = true
  try {
    await api.setSessionModel(sessionId.value, modelId)
    if (modelState.value) modelState.value = { ...modelState.value, currentModelId: modelId }
  } catch (err) {
    showError(err, 'Failed to update ACP model')
  } finally {
    updatingSessionConfig.value = false
  }
}

async function updateConfigOption(option: SessionConfigOption, value: boolean | string) {
  if (value === option.currentValue) return
  updatingSessionConfig.value = true
  try {
    const result = await api.setSessionConfigOption(
      sessionId.value,
      option.id,
      option.type === 'boolean' ? { type: 'boolean', value: Boolean(value) } : { value: String(value) }
    )
    if (result.configOptions.length) {
      configOptions.value = result.configOptions
    } else {
      configOptions.value = configOptions.value.map((item) => {
        if (item.id !== option.id) return item
        return item.type === 'boolean'
          ? { ...item, currentValue: Boolean(value) }
          : { ...item, currentValue: String(value) }
      })
    }
  } catch (err) {
    showError(err, `Failed to update ${option.name}`)
  } finally {
    updatingSessionConfig.value = false
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
        <div
          ref="messagesScrollContainer"
          class="min-h-0 flex-1 overflow-y-auto px-4 py-6"
          :style="messagesScrollShadowStyle"
        >
          <div
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
                @click="loadOlderMessages"
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
                  @click="respondToPermission(permission.appRequestId, option)"
                >
                  {{ option.name }}
                </UButton>
                <UButton
                  size="sm"
                  color="neutral"
                  variant="ghost"
                  @click="respondToPermission(permission.appRequestId)"
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
              :status="submitStatus"
              :should-auto-scroll="true"
              :should-scroll-to-bottom="true"
              :auto-scroll="true"
              auto-scroll-icon="i-lucide-arrow-down"
              :user="chatUserProps"
              :assistant="chatAssistantProps"
            >
              <template #content="{ message }: { message: AcpChatMessage }">
                <template v-if="message.role === 'user'">
                  <div
                    v-if="editingMessageId === message.id"
                    :ref="element => setEditingMessageContainer(element)"
                    class="min-w-[min(28rem,calc(100vw-4rem))] space-y-2"
                  >
                    <UTextarea
                      v-model="editingText"
                      :maxrows="10"
                      autofocus
                      autoresize
                      class="w-full"
                      :disabled="submitting || savingEditedMessageId === message.id"
                      @keydown.esc.prevent="cancelEditingUserMessage"
                      @keydown.meta.enter.prevent="saveEditedUserMessage(message)"
                      @keydown.ctrl.enter.prevent="saveEditedUserMessage(message)"
                    />
                    <div class="flex justify-end gap-2">
                      <UButton
                        size="xs"
                        color="neutral"
                        variant="ghost"
                        label="Cancel"
                        :disabled="savingEditedMessageId === message.id"
                        @click="cancelEditingUserMessage"
                      />
                      <UButton
                        size="xs"
                        color="primary"
                        label="Send edited"
                        :loading="savingEditedMessageId === message.id"
                        :disabled="!editingText.trim() || submitting"
                        @click="saveEditedUserMessage(message)"
                      />
                    </div>
                  </div>
                  <template v-else>
                    {{ partText(message) }}
                  </template>
                </template>
                <div
                  v-else
                  class="inline-block max-w-full"
                  @pointerenter="setAssistantMessageHover(message.id, true)"
                  @pointerleave="event => onAssistantMessagePointerLeave(event, message.id)"
                  @focusin="focusedAssistantMessageId = message.id"
                  @focusout="event => onAssistantMessageFocusOut(event, message.id)"
                >
                  <UChatTool
                    v-if="shouldRenderRunDetailsBeforeMessage(message)"
                    text="Run details"
                    :suffix="runDetailSummary(message)"
                    :icon="toolParts(message).some(part => part.error) ? 'i-lucide-circle-alert' : 'i-lucide-list-tree'"
                    variant="card"
                    chevron="trailing"
                    :default-open="isActiveRunDetailMessage(message)"
                    :ref="element => setRunDetailsElement(message.id, element)"
                    :class="runDetailsSpacingClass(message, 'before')"
                    :ui="{
                      root: 'bg-muted/20',
                      trigger: 'px-3 py-2',
                      leadingIcon: toolParts(message).some(part => part.error) ? 'text-error' : 'text-dimmed',
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
                    :workspace="context.selectedWorkspace.value"
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
                          @click.stop.prevent="action.onClick($event, message as AcpChatMessageWithActions)"
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
                          @click="action.onClick($event, message as AcpChatMessageWithActions)"
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
                    :icon="toolParts(message).some(part => part.error) ? 'i-lucide-circle-alert' : 'i-lucide-list-tree'"
                    variant="card"
                    chevron="trailing"
                    :default-open="isActiveRunDetailMessage(message)"
                    :ref="element => setRunDetailsElement(message.id, element)"
                    :class="runDetailsSpacingClass(message, 'after')"
                    :ui="{
                      root: 'bg-muted/20',
                      trigger: 'px-3 py-2',
                      leadingIcon: toolParts(message).some(part => part.error) ? 'text-error' : 'text-dimmed',
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
              <template #actions="{ message }: { message: AcpChatMessageWithActions }">
                <div
                  v-if="message.role === 'user' && editingMessageId !== message.id && (messageMetadataItems(message).length || message.actions?.length)"
                  class="flex flex-wrap items-center justify-end gap-x-1.5 gap-y-1 text-xs leading-none text-muted"
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

        <div class="shrink-0 bg-default/80 px-4 py-4 backdrop-blur">
          <div class="mx-auto w-full max-w-3xl">
            <div ref="promptContainer" class="relative">
              <ChatSlashCommandMenu
                :commands="slashCommands.filteredCommands.value"
                :open="slashCommands.isOpen.value"
                :loading="slashCommands.loading.value"
                :highlighted-index="slashCommands.highlightedIndex.value"
                @select="selectSlashCommand"
                @highlight="slashCommands.highlightedIndex.value = $event"
              />
              <div
                v-if="queuedForSession.length"
                class="absolute inset-x-0 bottom-full z-10 pb-2"
              >
                <ChatQueuedMessages
                  :messages="queuedForSession"
                  :steering-id="steeringQueuedMessageId"
                  :disabled="loading"
                  @edit="editQueuedMessage"
                  @delete="deleteQueuedMessage"
                  @steer="steerQueuedMessage"
                />
              </div>
              <UChatPrompt
                v-model="input"
                :maxrows="6"
                :should-auto-scroll="true"
                :should-scroll-to-bottom="true"
                :auto-scroll="true"
                placeholder="Message Hermes through ACP…"
                @submit="onSubmit"
                @keydown.down="onPromptArrowDown"
                @keydown.up="onPromptArrowUp"
                @keydown.esc="onPromptEscape"
                @keydown.enter="onPromptAutocompleteEnter"
              >
              <template #footer>
                <AcpChatPromptFooter
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
                  @stop="stopPrompt"
                  @attach-files="attachFiles"
                  @remove-attachment="context.removeAttachment"
                  @voice-text="appendVoiceText"
                  @voice-error="showVoiceError"
                  @update-selected-workspace="context.selectWorkspace"
                  @update-selected-model="updateSessionModel"
                  @update-selected-mode="updateSessionMode"
                />
              </template>
              </UChatPrompt>
            </div>
          </div>
        </div>
      </div>
    </template>
  </UDashboardPanel>
</template>
