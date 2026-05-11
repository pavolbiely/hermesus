import { nextTick, ref, type Ref } from 'vue'
import type { PlanEntry } from '@agentclientprotocol/sdk'
import type {
  AcpBridgeEvent,
  AvailableCommand,
  PermissionOption,
  RequestPermissionRequest,
  SessionConfigOption,
  SessionModeState,
  SessionModelState
} from '~/types/acp-api'
import type { AcpChatMessage } from '~/types/acp-chat'
import type { PendingAcpPrompt } from '~/composables/useAcpPromptAttachments'
import type { ChatPromptAttachment } from '~/types/chat'
import { isAcpPlanUpdate, normalizeAcpPlanEntries } from '~/utils/acpPlanNormalization'
import { scrollElementTreeToBottom, scrollElementTreeToBottomAfterRender } from '~/utils/chatInitialScroll'

type PendingPermission = {
  appRequestId: string
  request: RequestPermissionRequest
}

type ChatSubmitStatus = 'ready' | 'submitted' | 'streaming'

type AcpSessionPageApi = {
  loadSession: (sessionId: string, options?: { signal?: AbortSignal }) => Promise<{
    models?: SessionModelState | null
    modes?: SessionModeState | null
    configOptions?: SessionConfigOption[] | null
    availableCommands?: AvailableCommand[] | null
    events: AcpBridgeEvent[]
  }>
  subscribeSession: (
    sessionId: string,
    onEvent: (event: AcpBridgeEvent) => void,
    onError?: (event: Event) => void,
    options?: { afterSequence?: number, replay?: boolean }
  ) => EventSource
  respondToPermission: (appRequestId: string, payload: { optionId?: string, cancelled?: boolean }) => Promise<unknown>
}

type AcpSessionPageOptions = {
  sessionId: Ref<string>
  messagesScrollContainer: Ref<HTMLElement | null>
  pendingPrompts: Ref<Record<string, PendingAcpPrompt>>
  queryPrompt: Ref<string>
  replaceRouteQuery: () => Promise<unknown>
  loadSession: AcpSessionPageApi['loadSession']
  subscribeSession: AcpSessionPageApi['subscribeSession']
  respondToPermissionRequest: AcpSessionPageApi['respondToPermission']
  transcript: {
    state: Ref<{ cursor?: number, messages: AcpChatMessage[] }>
    reset: () => void
    prependMessages: (messages: AcpChatMessage[]) => void
    applyBridgeEvent: (event: AcpBridgeEvent) => void
  }
  modelState: Ref<SessionModelState | null>
  modeState: Ref<SessionModeState | null>
  configOptions: Ref<SessionConfigOption[]>
  availableCommands: Ref<AvailableCommand[]>
  activePromptTurnId: Ref<string | null>
  submitStatusState: Ref<ChatSubmitStatus>
  activePrompts: {
    markFinished: (sessionId: string, turnId?: string | null) => void
  }
  onPromptRequested: (message: string, attachments?: ChatPromptAttachment[]) => Promise<unknown>
  onSessionTouched: (sessionId: string) => void
  showError: (err: unknown, fallback: string) => void
  waitForFrame: () => Promise<void>
}


export function useAcpSessionPage(options: AcpSessionPageOptions) {
  const loading = ref(true)
  const initialTranscriptScrollPending = ref(true)
  const pendingPermissions = ref<PendingPermission[]>([])
  const planEntries = ref<PlanEntry[]>([])
  const loadingOlderMessages = ref(false)
  const hasOlderMessages = ref(false)
  const nextTranscriptBefore = ref<number | null>(null)
  const error = ref<string | null>(null)

  let closeEvents: (() => void) | undefined
  let eventSource: EventSource | undefined
  let sessionLoadSequence = 0
  let sessionLoadAbortController: AbortController | undefined
  let latestInitialScrollSequence = 0

  async function initializeSession(targetSessionId = options.sessionId.value) {
    if (!targetSessionId) return

    abortActiveSessionLoad()
    closeEvents?.()
    closeEvents = undefined
    eventSource = undefined

    const loadSequence = ++sessionLoadSequence
    const abortController = new AbortController()
    sessionLoadAbortController = abortController

    loading.value = true
    initialTranscriptScrollPending.value = true
    error.value = null
    resetSessionView()

    try {
      const loaded = await options.loadSession(targetSessionId, { signal: abortController.signal })
      if (!isCurrentSessionLoad(loadSequence, targetSessionId, abortController)) return

      options.modelState.value = loaded.models || options.modelState.value
      options.modeState.value = loaded.modes || options.modeState.value
      options.configOptions.value = loaded.configOptions || options.configOptions.value
      options.availableCommands.value = loaded.availableCommands || options.availableCommands.value
      loaded.events.forEach(handleBridgeEvent)
      scrollInitialTranscriptToBottom(loadSequence, targetSessionId)

      subscribeToSessionEvents(targetSessionId)
      await processQueuedPrompt(targetSessionId)
    } catch (err) {
      if (isAbortError(err)) return
      if (!isCurrentSessionLoad(loadSequence, targetSessionId, abortController)) return
      options.showError(err, 'Could not load ACP session')
    } finally {
      if (sessionLoadAbortController === abortController) sessionLoadAbortController = undefined
      if (isCurrentSessionLoad(loadSequence, targetSessionId, abortController)) {
        loading.value = false
      }
    }
  }

  function subscribeToSessionEvents(targetSessionId: string) {
    const replayOptions = options.transcript.state.value.cursor === undefined
      ? { replay: false }
      : { afterSequence: options.transcript.state.value.cursor }
    eventSource = options.subscribeSession(targetSessionId, handleBridgeEvent, () => {
      if (targetSessionId === options.sessionId.value) error.value ||= 'ACP event stream disconnected.'
    }, replayOptions)
    closeEvents = () => eventSource?.close()
  }

  async function processQueuedPrompt(targetSessionId: string) {
    const queuedPrompt = options.pendingPrompts.value[targetSessionId]
    if (queuedPrompt) {
      delete options.pendingPrompts.value[targetSessionId]
      await options.replaceRouteQuery()
      await options.onPromptRequested(queuedPrompt.message, queuedPrompt.attachments)
      return
    }

    const queuedPromptText = options.queryPrompt.value
    if (queuedPromptText.trim()) {
      await options.replaceRouteQuery()
      await options.onPromptRequested(queuedPromptText)
    }
  }

  function abortActiveSessionLoad() {
    sessionLoadAbortController?.abort()
    sessionLoadAbortController = undefined
    latestInitialScrollSequence++
  }

  function closeSessionEvents() {
    closeEvents?.()
    closeEvents = undefined
    eventSource = undefined
  }

  function isCurrentSessionLoad(loadSequence: number, targetSessionId: string, abortController: AbortController) {
    return !abortController.signal.aborted
      && loadSequence === sessionLoadSequence
      && targetSessionId === options.sessionId.value
  }

  function isAbortError(err: unknown) {
    return (typeof DOMException !== 'undefined' && err instanceof DOMException && err.name === 'AbortError')
      || (err instanceof Error && err.name === 'AbortError')
  }

  function scrollInitialTranscriptToBottom(loadSequence: number, targetSessionId: string) {
    if (!import.meta.client) return

    const scrollSequence = ++latestInitialScrollSequence
    const isCurrentLoad = () => (
      scrollSequence === latestInitialScrollSequence
      && loadSequence === sessionLoadSequence
      && targetSessionId === options.sessionId.value
    )

    void (async () => {
      await nextTick()
      if (!isCurrentLoad()) return

      scrollElementTreeToBottom(options.messagesScrollContainer.value)

      await scrollElementTreeToBottomAfterRender(options.messagesScrollContainer.value, {
        waitForFrame: options.waitForFrame,
        stableFrameCount: 2,
        maxFrameCount: 10
      })

      if (isCurrentLoad()) initialTranscriptScrollPending.value = false
    })()
  }

  function resetSessionView() {
    initialTranscriptScrollPending.value = true
    options.transcript.reset()
    pendingPermissions.value = []
    planEntries.value = []
    options.modelState.value = null
    options.modeState.value = null
    options.configOptions.value = []
    options.availableCommands.value = []
    loadingOlderMessages.value = false
    hasOlderMessages.value = false
    nextTranscriptBefore.value = null
    options.activePromptTurnId.value = null
    options.submitStatusState.value = 'ready'
  }

  async function loadOlderMessages() {
    return Promise.resolve()
  }

  function handleBridgeEvent(event: AcpBridgeEvent) {
    if (event.sessionId !== options.sessionId.value) return
    options.onSessionTouched(event.sessionId)
    options.transcript.applyBridgeEvent(event)
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
      if (update.sessionUpdate === 'current_mode_update' && options.modeState.value) {
        options.modeState.value = { ...options.modeState.value, currentModeId: update.currentModeId }
      }
      if (update.sessionUpdate === 'config_option_update') {
        options.configOptions.value = update.configOptions
      }
      if (update.sessionUpdate === 'available_commands_update') {
        options.availableCommands.value = update.availableCommands
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
      if (!('turnId' in event) || event.turnId === options.activePromptTurnId.value) {
        options.activePrompts.markFinished(event.sessionId, 'turnId' in event ? event.turnId : null)
        options.activePromptTurnId.value = null
      }
    }
  }

  async function respondToPermission(appRequestId: string, option?: PermissionOption) {
    try {
      await options.respondToPermissionRequest(appRequestId, option ? { optionId: option.optionId } : { cancelled: true })
    } catch (err) {
      options.showError(err, 'Failed to respond to permission request')
    }
  }

  return {
    loading,
    initialTranscriptScrollPending,
    pendingPermissions,
    planEntries,
    loadingOlderMessages,
    hasOlderMessages,
    nextTranscriptBefore,
    error,
    initializeSession,
    abortActiveSessionLoad,
    closeSessionEvents,
    loadOlderMessages,
    respondToPermission
  }
}
