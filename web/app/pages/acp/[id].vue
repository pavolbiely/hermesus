<script setup lang="ts">
import type { PlanEntry } from '@agentclientprotocol/sdk'
import type {
  AvailableCommand,
  AcpTranscriptSnapshot,
  PermissionOption,
  RequestPermissionRequest,
  SessionConfigOption,
  SessionModeState,
  SessionModelState
} from '~/types/acp-api'
import type { AcpChatMessage } from '~/types/acp-chat'
import type { ChatPromptAttachment, SlashCommand } from '~/types/chat'
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
import { scrollElementTreeToBottom, scrollElementTreeToBottomAfterRender } from '~/utils/chatInitialScroll'
import { toolCallTitle } from '~/utils/toolCalls'

type PendingPermission = {
  appRequestId: string
  request: RequestPermissionRequest
}

type CachedSessionView = {
  transcript: AcpTranscriptSnapshot
  hasOlderMessages: boolean
  nextTranscriptBefore: number | null
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

type AcpToolPart = Extract<AcpChatMessage['parts'][number], { type: 'tool' }>

const route = useRoute()
const router = useRouter()
const api = useAcpApi()
const context = useChatComposerContext()
const pendingAcpPrompts = usePendingAcpPrompt()
const transcript = useAcpTranscript()
const sessionViewCache = useState<Record<string, CachedSessionView>>('acp-session-view-cache', () => ({}))
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
const activePromptTurnId = ref<string | null>(null)
const pendingPermissions = ref<PendingPermission[]>([])
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
let sessionLoadSequence = 0
let sessionLoadAbortController: AbortController | undefined
let displayedSessionId: string | null = null
let latestInitialScrollSequence = 0

const transcriptPageSize = 80

const submitting = computed(() => Boolean(activePromptTurnId.value))
const submitStatus = computed(() => submitting.value ? 'streaming' : 'ready')
const messages = computed(() => transcript.messages.value)
const displayMessages = computed<AcpChatMessageWithActions[]>(() => groupProcessMessages(messages.value).map(withNativeMessageActions))
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
  return [...displayMessages.value].reverse().find(message => message.turnId === activePromptTurnId.value && hasRunDetails(message)) || null
})
const currentActivityLabel = computed(() => {
  const activeMessage = activeRunMessage.value
  if (!activePromptTurnId.value) return null
  if (!activeMessage) return 'Starting…'
  return runActivityLabel(activeMessage) || 'Working…'
})
const showRunActivityIndicator = computed(() => Boolean(currentActivityLabel.value))
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
  return option ? configOptionItems(option) : modeItems.value
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
  cacheCurrentSessionView(displayedSessionId)
  abortActiveSessionLoad()
  closeEvents?.()
  runDetailsScrollCleanup.forEach(cleanup => cleanup())
  runDetailsScrollCleanup.clear()
})

watch(sessionId, (newSessionId) => {
  void initializeSession(newSessionId)
})

async function initializeSession(targetSessionId = sessionId.value) {
  if (!targetSessionId) return

  cacheCurrentSessionView(displayedSessionId)
  abortActiveSessionLoad()
  closeEvents?.()
  closeEvents = undefined
  eventSource = undefined

  const loadSequence = ++sessionLoadSequence
  const abortController = new AbortController()
  sessionLoadAbortController = abortController
  displayedSessionId = targetSessionId

  loading.value = true
  error.value = null
  resetSessionView()

  const cached = sessionViewCache.value[targetSessionId]
  if (cached) {
    restoreCachedSessionView(cached)
    loading.value = false
    scrollInitialTranscriptToBottom(loadSequence, targetSessionId)
  }

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
      cacheCurrentSessionView(targetSessionId)
      scrollInitialTranscriptToBottom(loadSequence, targetSessionId)
    }

    eventSource = api.subscribeSession(targetSessionId, handleBridgeEvent, () => {
      if (targetSessionId === sessionId.value) error.value ||= 'ACP event stream disconnected.'
    })
    closeEvents = () => eventSource?.close()

    const loaded = await api.loadSession(targetSessionId, { signal: abortController.signal })
    if (!isCurrentSessionLoad(loadSequence, targetSessionId, abortController)) return

    modelState.value = loaded.models || modelState.value
    modeState.value = loaded.modes || modeState.value
    configOptions.value = loaded.configOptions || configOptions.value
    if (initializedFromProjection) {
      const refreshed = await api.readTranscript(
        targetSessionId,
        { limit: transcriptPageSize },
        { signal: abortController.signal }
      )
      if (!isCurrentSessionLoad(loadSequence, targetSessionId, abortController)) return
      if (refreshed.transcript) {
        applyTranscriptSnapshot(refreshed.transcript)
        hasOlderMessages.value = refreshed.hasMore
        nextTranscriptBefore.value = refreshed.nextBefore
        cacheCurrentSessionView(targetSessionId)
        scrollInitialTranscriptToBottom(loadSequence, targetSessionId)
      }
    } else {
      loaded.events.forEach(handleBridgeEvent)
      cacheCurrentSessionView(targetSessionId)
      scrollInitialTranscriptToBottom(loadSequence, targetSessionId)
    }

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

async function onSubmit() {
  const message = input.value.trim()
  if ((!message && !context.attachments.value.length) || submitting.value) return
  const attachments = context.attachments.value
  input.value = ''
  context.clearAttachments()
  await sendPrompt(message, attachments)
}

function abortActiveSessionLoad() {
  sessionLoadAbortController?.abort()
  sessionLoadAbortController = undefined
  latestInitialScrollSequence++
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

function restoreCachedSessionView(view: CachedSessionView) {
  applyTranscriptSnapshot(clonePlain(view.transcript))
  hasOlderMessages.value = view.hasOlderMessages
  nextTranscriptBefore.value = view.nextTranscriptBefore
}

function cacheCurrentSessionView(targetSessionId: string | null) {
  if (!targetSessionId || displayedSessionId !== targetSessionId) return
  if (!messages.value.length && !pendingPermissions.value.length && !planEntries.value.length) return

  sessionViewCache.value = {
    ...sessionViewCache.value,
    [targetSessionId]: clonePlain({
      transcript: {
        sessionId: targetSessionId,
        cursor: transcript.state.value.cursor,
        updatedAt: new Date().toISOString(),
        messages: transcript.messages.value,
        pendingPermissions: pendingPermissions.value,
        planEntries: planEntries.value,
        prompt: activePromptTurnId.value
          ? { status: 'running', turnId: activePromptTurnId.value }
          : null,
        models: modelState.value,
        modes: modeState.value,
        configOptions: configOptions.value,
        availableCommands: availableCommands.value
      },
      hasOlderMessages: hasOlderMessages.value,
      nextTranscriptBefore: nextTranscriptBefore.value
    })
  }
}

function clonePlain<T>(value: T): T {
  try {
    return structuredClone(value)
  } catch {
    return JSON.parse(JSON.stringify(value)) as T
  }
}

async function sendPrompt(message: string, attachments: ChatPromptAttachment[] = []) {
  error.value = null
  const turnId = crypto.randomUUID()
  const messageId = crypto.randomUUID()
  activePromptTurnId.value = turnId
  transcript.applyEvent({
    type: 'user.message',
    eventId: `optimistic-user:${turnId}`,
    sessionId: sessionId.value,
    turnId,
    messageId,
    text: message,
    occurredAt: new Date().toISOString()
  })
  cacheCurrentSessionView(sessionId.value)

  try {
    await api.startPrompt(sessionId.value, {
      prompt: attachmentsToPromptBlocks(message || 'See attached files.', attachments),
      turnId,
      messageId
    })
  } catch (err) {
    if (activePromptTurnId.value === turnId) activePromptTurnId.value = null
    showError(err, 'Failed to send prompt')
  }
}

async function stopPrompt() {
  if (!submitting.value) return
  try {
    await api.cancel(sessionId.value)
  } catch (err) {
    showError(err, 'Failed to cancel prompt')
  } finally {
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
  })()
}

function waitForAnimationFrame() {
  return new Promise<void>((resolve) => {
    requestAnimationFrame(() => resolve())
  })
}

function resetSessionView() {
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
    cacheCurrentSessionView(sessionId.value)
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
      activePromptTurnId.value = null
    }
  }
  cacheCurrentSessionView(event.sessionId)
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
  if (message.role !== 'user' || !text || message.turnId === activePromptTurnId.value) return message

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
        onClick: () => editUserMessage(message)
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

function hasAssistantFooter(message: AcpChatMessage) {
  return messageMetadataItems(message).length > 0 || assistantMessageActions(message).length > 0
}

function messageMetadataItems(message: AcpChatMessage) {
  if (
    message.role !== 'assistant'
    || message.turnId === activePromptTurnId.value
    || !acpMessageText(message).trim()
  ) return []

  const items: Array<{ key: string, label: string, title?: string }> = []
  if (message.createdAt) {
    items.push({
      key: 'time',
      label: formatAcpMessageTimestamp(message.createdAt),
      title: acpMessageTimestampDetails(message.createdAt)
    })
  }

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

async function editUserMessage(message: AcpChatMessage) {
  const text = acpMessageText(message).trim()
  if (!text || submitting.value) return

  input.value = text
  await nextTick()
  promptContainer.value?.querySelector('textarea')?.focus()
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

function reasoningText(message: AcpChatMessage) {
  return message.parts.filter(part => part.type === 'reasoning').map(part => part.text).join('')
}

function hasThoughtActivity(message: AcpChatMessage) {
  return Boolean(reasoningText(message).trim() || thoughtTokenCount(message))
}

function thoughtTokenCount(message: AcpChatMessage) {
  return message.usage?.thoughtTokens && message.usage.thoughtTokens > 0 ? message.usage.thoughtTokens : 0
}

function thoughtDetail(message: AcpChatMessage) {
  const tokens = thoughtTokenCount(message)
  if (!tokens) return ''
  return `${tokens.toLocaleString()} thought token${tokens === 1 ? '' : 's'} were used for this turn. Hermes ACP did not expose the raw thought text for this model response.`
}

function toolParts(message: AcpChatMessage): AcpToolPart[] {
  return message.parts.filter((part): part is AcpToolPart => part.type === 'tool')
}

function runDetailSummary(message: AcpChatMessage) {
  const tools = toolParts(message)
  const failed = tools.filter(part => part.error || part.status === 'failed').length
  const running = runningToolParts(message).length
  const completed = tools.length - failed - running
  const parts: string[] = []
  if (hasThoughtActivity(message)) parts.push('Reasoned')
  if (running) parts.push(`${running} running`)
  if (completed) parts.push(`${completed} completed`)
  if (failed) parts.push(`${failed} failed`)
  return parts.join(' · ')
}

function runningToolParts(message: AcpChatMessage) {
  return toolParts(message).filter(part => part.state !== 'completed' && !part.error)
}

function runActivityLabel(message: AcpChatMessage) {
  const runningTool = runningToolParts(message)[0]
  if (runningTool) return `Running ${toolCallTitle(runningTool)}`
  if (message.turnId && message.turnId === activePromptTurnId.value && reasoningText(message).trim()) return 'Thinking'
  return ''
}

function hasRunDetails(message: AcpChatMessage) {
  return toolParts(message).length > 0 || hasThoughtActivity(message)
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
      return item.options.map(child => ({ label: `${item.name}: ${child.name}`, value: child.value }))
    }
    return [{ label: item.name, value: item.value }]
  })
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
      <AppNavbar title="ACP chat" />
    </template>

    <template #body>
      <div class="flex h-full min-h-0 flex-col">
        <div
          ref="messagesScrollContainer"
          class="min-h-0 flex-1 overflow-y-auto px-4 py-6"
          :style="messagesScrollShadowStyle"
        >
          <div class="mx-auto w-full max-w-3xl space-y-4">
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
                  {{ partText(message) }}
                </template>
                <div v-else>
                  <Comark
                    v-if="partText(message)"
                    :markdown="partText(message)"
                    class="prose prose-sm dark:prose-invert max-w-none"
                  />
                  <div
                    v-if="hasAssistantFooter(message)"
                    class="mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs leading-none text-muted transition-opacity focus-within:opacity-100"
                    :class="readAloudStatusDetail(message) ? 'opacity-100' : 'opacity-0 group-hover/message:opacity-100'"
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
                    v-if="hasRunDetails(message)"
                    text="Run details"
                    :suffix="runDetailSummary(message)"
                    :icon="toolParts(message).some(part => part.error) ? 'i-lucide-circle-alert' : 'i-lucide-list-tree'"
                    variant="card"
                    chevron="trailing"
                    :ref="element => setRunDetailsElement(message.id, element)"
                    :class="hasAssistantFooter(message) || partText(message) ? 'mt-4' : 'mt-2'"
                    :ui="{
                      root: 'bg-muted/20',
                      trigger: 'px-3 py-2',
                      leadingIcon: toolParts(message).some(part => part.error) ? 'text-error' : 'text-dimmed',
                      body: 'max-h-none space-y-2 overflow-visible border-t border-default p-3 text-sm text-dimmed whitespace-normal'
                    }"
                    @update:open="open => onRunDetailsOpen(open, message.id)"
                  >
                    <AcpThoughtItem
                      v-if="hasThoughtActivity(message)"
                      :text="reasoningText(message)"
                      :detail="thoughtDetail(message)"
                    />

                    <AcpToolCallItem
                      v-for="part in toolParts(message)"
                      :key="part.toolCallId"
                      :part="part"
                    />
                  </UChatTool>
                </div>
              </template>
              <template #actions="{ message }: { message: AcpChatMessageWithActions }">
                <div
                  v-if="message.role === 'user' && message.actions?.length"
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
                <AcpRunActivityIndicator :label="currentActivityLabel || 'Working…'" />
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
              <UChatPrompt
                v-model="input"
                :maxrows="6"
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
