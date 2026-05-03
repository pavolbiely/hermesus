import type { AgentStatusEvent, InteractivePrompt, WebChatRunEta, WebChatTaskPlan, WebChatWorkspaceChanges } from '~/types/web-chat'
import { reconcileRunSession } from '../utils/activeRunSession'
import { etaFromRunPayload, eventTimestamp, numericMetric, parseRunEventPayload, promptFromRunPayload, statusFromRunPayload, taskPlanFromRunPayload, type RunEventPayload } from '../utils/activeChatRunEvents'
import { notificationBodyPreview, showRunFinishedDesktopNotification } from '../utils/desktopNotifications'
import { notificationSoundVariant, playNotificationSound } from '../utils/notificationSound'
import { createRunEventReplay } from '../utils/runEventReplay'

type ToolRunPayload = { name?: string, preview?: string, input?: unknown, occurredAt?: string }
type RunLifecyclePayload = { message?: string, messageId?: string, occurredAt?: string }
type RunFailedPayload = RunLifecyclePayload & { error: string }
type RunSteeredPayload = { text?: string, messageId?: string, occurredAt?: string }

type CompletedRunPayload = {
  content?: string
  changes?: WebChatWorkspaceChanges | null
  tokenCount?: number | null
  inputTokens?: number | null
  outputTokens?: number | null
  cacheReadTokens?: number | null
  cacheWriteTokens?: number | null
  reasoningTokens?: number | null
  contextTokens?: number | null
  apiCalls?: number | null
  generationDurationMs?: number | null
  modelDurationMs?: number | null
  toolDurationMs?: number | null
  promptWaitDurationMs?: number | null
}

type ActiveRunHandlers = {
  onDelta?: (content: string) => void
  onReasoningDelta?: (content: string) => void
  onCompleted?: (payload: CompletedRunPayload) => void
  onToolStarted?: (payload: ToolRunPayload) => void
  onToolCompleted?: (payload: ToolRunPayload) => void
  onTaskPlanUpdated?: (payload: WebChatTaskPlan) => void
  onEtaUpdated?: (eta: WebChatRunEta) => void
  onStatus?: (payload: AgentStatusEvent) => void
  onPromptRequested?: (prompt: InteractivePrompt) => void
  onPromptUpdated?: (prompt: InteractivePrompt) => void
  onPromptExpired?: (prompt: InteractivePrompt) => void
  onPromptCancelled?: (prompt: InteractivePrompt) => void
  onRunStopped?: (payload: RunLifecyclePayload) => void
  onRunCompleted?: (payload: RunLifecyclePayload) => void
  onRunFailed?: (payload: RunFailedPayload) => void
  onRunSteered?: (payload: RunSteeredPayload) => void
  onSessionChanged?: (sessionId: string) => void
  onError?: (error: Error) => void
  onFinished?: () => void
}

type TrackedRun = {
  runId: string
  sessionId: string
  source: EventSource
  subscribers: Set<ActiveRunHandlers>
  replay: ReturnType<typeof createRunEventReplay>
  responsePreview?: string
  sessionTitle?: string
}

const trackedRuns = new Map<string, TrackedRun>()
const finishedRunIds = new Set<string>()
const finishedCallbacks = new Set<(sessionId: string, runId: string) => void | Promise<void>>()

function hermesToken() {
  if (import.meta.server) return undefined
  const runtimeToken = useRuntimeConfig().public.hermesSessionToken
  return window.__HERMES_SESSION_TOKEN__ || (typeof runtimeToken === 'string' ? runtimeToken : undefined)
}

function eventSourceUrl(runId: string) {
  const token = hermesToken()
  const url = new URL(`/api/web-chat/runs/${runId}/events`, window.location.origin)
  if (token) url.searchParams.set('session_token', token)
  return url.toString()
}

function notify(run: TrackedRun, notifySubscriber: (subscriber: ActiveRunHandlers) => void) {
  for (const subscriber of run.subscribers) notifySubscriber(subscriber)
}

function recordAndNotify<K extends keyof ActiveRunHandlers>(
  run: TrackedRun,
  handler: K,
  payload: Parameters<NonNullable<ActiveRunHandlers[K]>>[0]
) {
  run.replay.record(handler, payload)
  notify(run, subscriber => subscriber[handler]?.(payload as never))
}

function closeTrackedRun(runId: string) {
  const run = trackedRuns.get(runId)
  if (!run) return
  run.source.close()
  trackedRuns.delete(runId)
}

function isActiveVisibleChat(sessionId: string) {
  if (import.meta.server) return false
  return !document.hidden && document.hasFocus() && window.location.pathname === `/chat/${sessionId}`
}

function isLatestContentVisible() {
  if (import.meta.server) return false
  const chatPanel = [...document.querySelectorAll<HTMLElement>('*')]
    .find(element => element.scrollHeight > element.clientHeight && getComputedStyle(element).overflowY !== 'visible' && element.getBoundingClientRect().left > 200)
  if (!chatPanel) return true

  return chatPanel.scrollHeight - chatPanel.clientHeight - chatPanel.scrollTop < 48
}

function runNotificationVariant(sessionId: string) {
  return notificationSoundVariant({
    activeVisibleChat: isActiveVisibleChat(sessionId),
    latestContentVisible: isLatestContentVisible()
  })
}

export function useActiveChatRuns() {
  const router = useRouter()
  const runningSessionIds = useState<string[]>('active-chat-run-session-ids', () => [])
  const localUnreadSessionIds = useState<string[]>('active-chat-local-unread-session-ids', () => [])
  const notificationOpenedSessionId = useState<string | null>('chat-notification-opened-session-id', () => null)

  function markRunning(sessionId: string) {
    if (!runningSessionIds.value.includes(sessionId)) {
      runningSessionIds.value = [...runningSessionIds.value, sessionId]
    }
  }

  function markFinished(sessionId: string) {
    runningSessionIds.value = runningSessionIds.value.filter(id => id !== sessionId)
  }

  function retargetRunFromEvent(run: TrackedRun, payload: RunEventPayload) {
    const oldSessionId = run.sessionId
    const oldSessionStillRunning = [...trackedRuns.values()].some(candidate => candidate !== run && candidate.sessionId === oldSessionId)
    const reconciled = reconcileRunSession({
      trackedSessionId: oldSessionId,
      eventSessionId: payload.sessionId,
      runningSessionIds: runningSessionIds.value,
      oldSessionStillRunning
    })
    if (!reconciled.clearSubscribers) return

    notify(run, subscriber => subscriber.onSessionChanged?.(reconciled.sessionId))
    run.sessionId = reconciled.sessionId
    runningSessionIds.value = reconciled.runningSessionIds
    run.subscribers.clear()
  }

  function isRunning(sessionId: string) {
    return runningSessionIds.value.includes(sessionId)
  }

  function runIdForSession(sessionId: string) {
    return [...trackedRuns.values()].find(run => run.sessionId === sessionId)?.runId || null
  }

  function markLocalUnread(sessionId: string) {
    if (!localUnreadSessionIds.value.includes(sessionId)) {
      localUnreadSessionIds.value = [...localUnreadSessionIds.value, sessionId]
    }
  }

  function clearLocalUnread(sessionId: string) {
    localUnreadSessionIds.value = localUnreadSessionIds.value.filter(id => id !== sessionId)
  }

  function hasLocalUnread(sessionId: string) {
    return localUnreadSessionIds.value.includes(sessionId)
  }

  function setSessionTitle(sessionId: string, title: string | null | undefined) {
    const normalized = title?.trim()
    if (!normalized) return
    for (const run of trackedRuns.values()) {
      if (run.sessionId === sessionId) run.sessionTitle = normalized
    }
  }

  function finishRun(run: TrackedRun) {
    if (finishedRunIds.has(run.runId)) return

    closeTrackedRun(run.runId)
    finishedRunIds.add(run.runId)
    markFinished(run.sessionId)
    notify(run, subscriber => subscriber.onFinished?.())
    for (const callback of finishedCallbacks) void callback(run.sessionId, run.runId)
  }

  function clearSessionRun(sessionId: string) {
    const runs = [...trackedRuns.values()].filter(run => run.sessionId === sessionId)
    if (!runs.length) {
      markFinished(sessionId)
      return
    }

    for (const run of runs) finishRun(run)
  }

  function openSessionFromNotification(sessionId: string) {
    notificationOpenedSessionId.value = sessionId
    void router.push(`/chat/${sessionId}`)
  }

  function trackRun(sessionId: string, runId: string, options: { title?: string | null } = {}) {
    if (import.meta.server || finishedRunIds.has(runId)) return false

    markRunning(sessionId)
    const existingRun = trackedRuns.get(runId)
    if (existingRun) {
      if (options.title) setSessionTitle(sessionId, options.title)
      return true
    }

    const source = new EventSource(eventSourceUrl(runId))
    const run: TrackedRun = {
      runId,
      sessionId,
      source,
      subscribers: new Set(),
      replay: createRunEventReplay(),
      sessionTitle: options.title?.trim() || undefined
    }
    trackedRuns.set(runId, run)

    source.addEventListener('message.delta', (event) => {
      const payload = parseRunEventPayload(event)
      retargetRunFromEvent(run, payload)
      recordAndNotify(run, 'onDelta', String(payload.content || ''))
    })

    source.addEventListener('reasoning.delta', (event) => {
      const payload = parseRunEventPayload(event)
      retargetRunFromEvent(run, payload)
      recordAndNotify(run, 'onReasoningDelta', String(payload.content || ''))
    })

    source.addEventListener('message.completed', (event) => {
      const payload = parseRunEventPayload(event)
      retargetRunFromEvent(run, payload)
      const notificationVariant = runNotificationVariant(run.sessionId)
      playNotificationSound(notificationVariant)
      if (notificationVariant === 'attention') markLocalUnread(run.sessionId)
      run.responsePreview = notificationBodyPreview(typeof payload.content === 'string' ? payload.content : undefined)
      const metrics = payload.metrics && typeof payload.metrics === 'object' ? payload.metrics as Record<string, unknown> : {}
      recordAndNotify(run, 'onCompleted', {
        content: typeof payload.content === 'string' ? payload.content : undefined,
        changes: payload.changes && typeof payload.changes === 'object' ? payload.changes as WebChatWorkspaceChanges : null,
        tokenCount: numericMetric(metrics, 'tokenCount'),
        inputTokens: numericMetric(metrics, 'inputTokens'),
        outputTokens: numericMetric(metrics, 'outputTokens'),
        cacheReadTokens: numericMetric(metrics, 'cacheReadTokens'),
        cacheWriteTokens: numericMetric(metrics, 'cacheWriteTokens'),
        reasoningTokens: numericMetric(metrics, 'reasoningTokens'),
        contextTokens: numericMetric(metrics, 'contextTokens'),
        apiCalls: numericMetric(metrics, 'apiCalls'),
        generationDurationMs: numericMetric(metrics, 'generationDurationMs'),
        modelDurationMs: numericMetric(metrics, 'modelDurationMs'),
        toolDurationMs: numericMetric(metrics, 'toolDurationMs'),
        promptWaitDurationMs: numericMetric(metrics, 'promptWaitDurationMs')
      })
    })

    source.addEventListener('tool.started', (event) => {
      const payload = parseRunEventPayload(event)
      retargetRunFromEvent(run, payload)
      recordAndNotify(run, 'onToolStarted', {
        name: typeof payload.name === 'string' ? payload.name : undefined,
        preview: typeof payload.preview === 'string' ? payload.preview : undefined,
        input: payload.input,
        occurredAt: eventTimestamp()
      })
    })

    source.addEventListener('tool.completed', (event) => {
      const payload = parseRunEventPayload(event)
      retargetRunFromEvent(run, payload)
      recordAndNotify(run, 'onToolCompleted', {
        name: typeof payload.name === 'string' ? payload.name : undefined,
        preview: typeof payload.preview === 'string' ? payload.preview : undefined,
        input: payload.input,
        occurredAt: eventTimestamp()
      })
    })

    source.addEventListener('task_plan.updated', (event) => {
      const payload = parseRunEventPayload(event)
      retargetRunFromEvent(run, payload)
      const taskPlan = taskPlanFromRunPayload(payload)
      if (!taskPlan) return
      recordAndNotify(run, 'onTaskPlanUpdated', taskPlan)
    })

    source.addEventListener('eta.updated', (event) => {
      const payload = parseRunEventPayload(event)
      retargetRunFromEvent(run, payload)
      const eta = etaFromRunPayload(payload)
      if (!eta) return
      recordAndNotify(run, 'onEtaUpdated', eta)
    })

    source.addEventListener('agent.status', (event) => {
      const payload = parseRunEventPayload(event)
      retargetRunFromEvent(run, payload)
      const status = statusFromRunPayload(payload)
      if (!status) return
      recordAndNotify(run, 'onStatus', status)
    })

    source.addEventListener('prompt.requested', (event) => {
      const payload = parseRunEventPayload(event)
      retargetRunFromEvent(run, payload)
      const prompt = promptFromRunPayload(payload)
      if (!prompt) return
      if (!isActiveVisibleChat(run.sessionId)) markLocalUnread(run.sessionId)
      playNotificationSound(runNotificationVariant(run.sessionId))
      recordAndNotify(run, 'onPromptRequested', prompt)
    })

    const updatePrompt = (event: Event) => {
      const payload = parseRunEventPayload(event)
      retargetRunFromEvent(run, payload)
      const prompt = promptFromRunPayload(payload)
      if (!prompt) return
      recordAndNotify(run, 'onPromptUpdated', prompt)
    }

    source.addEventListener('prompt.answered', updatePrompt)
    source.addEventListener('prompt.expired', (event) => {
      updatePrompt(event)
      const prompt = promptFromRunPayload(parseRunEventPayload(event))
      if (prompt) recordAndNotify(run, 'onPromptExpired', prompt)
    })
    source.addEventListener('prompt.cancelled', (event) => {
      updatePrompt(event)
      const prompt = promptFromRunPayload(parseRunEventPayload(event))
      if (prompt) recordAndNotify(run, 'onPromptCancelled', prompt)
    })

    source.addEventListener('run.completed', (event) => {
      const payload = parseRunEventPayload(event)
      retargetRunFromEvent(run, payload)
      recordAndNotify(run, 'onRunCompleted', {
        message: typeof payload.message === 'string' ? payload.message : undefined,
        messageId: typeof payload.messageId === 'string' ? payload.messageId : undefined,
        occurredAt: eventTimestamp()
      })
      showRunFinishedDesktopNotification({
        sessionId: run.sessionId,
        runId: run.runId,
        status: 'completed',
        responsePreview: run.responsePreview,
        chatTitle: run.sessionTitle,
        onClick: openSessionFromNotification
      })
      finishRun(run)
    })
    source.addEventListener('run.stopped', (event) => {
      const payload = parseRunEventPayload(event)
      retargetRunFromEvent(run, payload)
      recordAndNotify(run, 'onRunStopped', {
        message: typeof payload.message === 'string' ? payload.message : undefined,
        messageId: typeof payload.messageId === 'string' ? payload.messageId : undefined,
        occurredAt: eventTimestamp()
      })
      finishRun(run)
    })

    source.addEventListener('run.steered', (event) => {
      const payload = parseRunEventPayload(event)
      retargetRunFromEvent(run, payload)
      recordAndNotify(run, 'onRunSteered', {
        text: typeof payload.text === 'string' ? payload.text : undefined,
        messageId: typeof payload.messageId === 'string' ? payload.messageId : undefined,
        occurredAt: eventTimestamp()
      })
    })

    source.addEventListener('run.failed', (event) => {
      const payload = parseRunEventPayload(event)
      retargetRunFromEvent(run, payload)
      const errorMessage = typeof payload.error === 'string' ? payload.error : 'Run failed'
      recordAndNotify(run, 'onRunFailed', {
        error: errorMessage,
        messageId: typeof payload.messageId === 'string' ? payload.messageId : undefined,
        occurredAt: eventTimestamp()
      })
      const error = new Error(errorMessage)
      notify(run, subscriber => subscriber.onError?.(error))
      showRunFinishedDesktopNotification({
        sessionId: run.sessionId,
        runId: run.runId,
        status: 'failed',
        chatTitle: run.sessionTitle,
        onClick: openSessionFromNotification
      })
      finishRun(run)
    })

    source.onerror = () => {
      // EventSource also reports transient disconnects while it is reconnecting.
      // Treat only explicit `run.failed` events as failed runs; otherwise a normal
      // reconnect/stop transition can incorrectly disable the composer and show a
      // false failure toast.
    }

    return true
  }

  function subscribe(sessionId: string, handlers: ActiveRunHandlers) {
    const runs = [...trackedRuns.values()].filter(run => run.sessionId === sessionId)
    for (const run of runs) {
      run.subscribers.add(handlers)
      run.replay.replay(handlers)
    }

    return () => {
      for (const run of runs) run.subscribers.delete(handlers)
    }
  }

  async function stop(sessionId: string) {
    const run = [...trackedRuns.values()].find(run => run.sessionId === sessionId)
    if (!run) return false

    await $fetch(`/api/web-chat/runs/${run.runId}/stop`, {
      method: 'POST',
      headers: hermesToken() ? { 'X-Hermes-Session-Token': hermesToken()! } : undefined
    })
    return true
  }

  function isRunFinished(runId: string) {
    return finishedRunIds.has(runId)
  }

  function onFinished(callback: (sessionId: string, runId: string) => void | Promise<void>) {
    finishedCallbacks.add(callback)
    return () => finishedCallbacks.delete(callback)
  }

  return {
    runningSessionIds,
    localUnreadSessionIds,
    markRunning,
    markFinished,
    isRunning,
    runIdForSession,
    markLocalUnread,
    clearLocalUnread,
    hasLocalUnread,
    setSessionTitle,
    trackRun,
    subscribe,
    stop,
    clearSessionRun,
    isRunFinished,
    onFinished
  }
}
