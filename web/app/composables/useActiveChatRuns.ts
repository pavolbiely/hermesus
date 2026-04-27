import type { AgentStatusEvent, InteractivePrompt, WebChatWorkspaceChanges } from '~/types/web-chat'
import { notificationSoundVariant, playNotificationSound } from '../utils/notificationSound'
import { createRunEventReplay } from '../utils/runEventReplay'

type RunEventPayload = Record<string, unknown>

type ToolRunPayload = { name?: string, preview?: string, input?: unknown }

type CompletedRunPayload = { content?: string, changes?: WebChatWorkspaceChanges | null }

type ActiveRunHandlers = {
  onDelta?: (content: string) => void
  onReasoningDelta?: (content: string) => void
  onCompleted?: (payload: CompletedRunPayload) => void
  onToolStarted?: (payload: ToolRunPayload) => void
  onToolCompleted?: (payload: ToolRunPayload) => void
  onStatus?: (payload: AgentStatusEvent) => void
  onPromptRequested?: (prompt: InteractivePrompt) => void
  onPromptUpdated?: (prompt: InteractivePrompt) => void
  onError?: (error: Error) => void
  onFinished?: () => void
}

type TrackedRun = {
  runId: string
  sessionId: string
  source: EventSource
  subscribers: Set<ActiveRunHandlers>
  replay: ReturnType<typeof createRunEventReplay>
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

function parsePayload(event: Event): RunEventPayload {
  return JSON.parse((event as MessageEvent).data)
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

function promptFromPayload(payload: RunEventPayload) {
  const prompt = payload.prompt
  return prompt && typeof prompt === 'object' ? prompt as InteractivePrompt : null
}

function statusFromPayload(payload: RunEventPayload): AgentStatusEvent | null {
  if (typeof payload.message !== 'string' || !payload.message) return null
  return {
    kind: typeof payload.kind === 'string' ? payload.kind : 'lifecycle',
    message: payload.message,
    createdAt: typeof payload.createdAt === 'string' ? payload.createdAt : null
  }
}

export function useActiveChatRuns() {
  const runningSessionIds = useState<string[]>('active-chat-run-session-ids', () => [])
  const promptUnreadSessionIds = useState<string[]>('active-chat-prompt-unread-session-ids', () => [])

  function markRunning(sessionId: string) {
    if (!runningSessionIds.value.includes(sessionId)) {
      runningSessionIds.value = [...runningSessionIds.value, sessionId]
    }
  }

  function markFinished(sessionId: string) {
    runningSessionIds.value = runningSessionIds.value.filter(id => id !== sessionId)
  }

  function isRunning(sessionId: string) {
    return runningSessionIds.value.includes(sessionId)
  }

  function runIdForSession(sessionId: string) {
    return [...trackedRuns.values()].find(run => run.sessionId === sessionId)?.runId || null
  }

  function markPromptUnread(sessionId: string) {
    if (!promptUnreadSessionIds.value.includes(sessionId)) {
      promptUnreadSessionIds.value = [...promptUnreadSessionIds.value, sessionId]
    }
  }

  function clearPromptUnread(sessionId: string) {
    promptUnreadSessionIds.value = promptUnreadSessionIds.value.filter(id => id !== sessionId)
  }

  function hasPromptUnread(sessionId: string) {
    return promptUnreadSessionIds.value.includes(sessionId)
  }

  function finishRun(run: TrackedRun) {
    if (finishedRunIds.has(run.runId)) return

    closeTrackedRun(run.runId)
    finishedRunIds.add(run.runId)
    markFinished(run.sessionId)
    notify(run, subscriber => subscriber.onFinished?.())
    for (const callback of finishedCallbacks) void callback(run.sessionId, run.runId)
  }

  function trackRun(sessionId: string, runId: string) {
    if (import.meta.server || finishedRunIds.has(runId)) return false

    markRunning(sessionId)
    if (trackedRuns.has(runId)) return true

    const source = new EventSource(eventSourceUrl(runId))
    const run: TrackedRun = {
      runId,
      sessionId,
      source,
      subscribers: new Set(),
      replay: createRunEventReplay()
    }
    trackedRuns.set(runId, run)

    source.addEventListener('message.delta', (event) => {
      const payload = parsePayload(event)
      recordAndNotify(run, 'onDelta', String(payload.content || ''))
    })

    source.addEventListener('reasoning.delta', (event) => {
      const payload = parsePayload(event)
      recordAndNotify(run, 'onReasoningDelta', String(payload.content || ''))
    })

    source.addEventListener('message.completed', (event) => {
      const payload = parsePayload(event)
      playNotificationSound(runNotificationVariant(run.sessionId))
      recordAndNotify(run, 'onCompleted', {
        content: typeof payload.content === 'string' ? payload.content : undefined,
        changes: payload.changes && typeof payload.changes === 'object' ? payload.changes as WebChatWorkspaceChanges : null
      })
    })

    source.addEventListener('tool.started', (event) => {
      const payload = parsePayload(event)
      recordAndNotify(run, 'onToolStarted', {
        name: typeof payload.name === 'string' ? payload.name : undefined,
        preview: typeof payload.preview === 'string' ? payload.preview : undefined,
        input: payload.input
      })
    })

    source.addEventListener('tool.completed', (event) => {
      const payload = parsePayload(event)
      recordAndNotify(run, 'onToolCompleted', {
        name: typeof payload.name === 'string' ? payload.name : undefined,
        preview: typeof payload.preview === 'string' ? payload.preview : undefined,
        input: payload.input
      })
    })

    source.addEventListener('agent.status', (event) => {
      const payload = statusFromPayload(parsePayload(event))
      if (!payload) return
      recordAndNotify(run, 'onStatus', payload)
    })

    source.addEventListener('prompt.requested', (event) => {
      const payload = parsePayload(event)
      const prompt = promptFromPayload(payload)
      if (!prompt) return
      if (!isActiveVisibleChat(run.sessionId)) markPromptUnread(run.sessionId)
      playNotificationSound(runNotificationVariant(run.sessionId))
      recordAndNotify(run, 'onPromptRequested', prompt)
    })

    const updatePrompt = (event: Event) => {
      const payload = parsePayload(event)
      const prompt = promptFromPayload(payload)
      if (!prompt) return
      recordAndNotify(run, 'onPromptUpdated', prompt)
    }

    source.addEventListener('prompt.answered', updatePrompt)
    source.addEventListener('prompt.expired', updatePrompt)
    source.addEventListener('prompt.cancelled', updatePrompt)

    source.addEventListener('run.completed', () => finishRun(run))
    source.addEventListener('run.stopped', () => finishRun(run))

    source.addEventListener('run.failed', (event) => {
      const payload = parsePayload(event)
      const error = new Error(typeof payload.error === 'string' ? payload.error : 'Run failed')
      notify(run, subscriber => subscriber.onError?.(error))
      finishRun(run)
    })

    source.onerror = () => {
      const error = new Error('Temporarily lost connection to Hermes run stream; reconnecting…')
      notify(run, subscriber => subscriber.onError?.(error))
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
    if (!run) return

    await $fetch(`/api/web-chat/runs/${run.runId}/stop`, {
      method: 'POST',
      headers: hermesToken() ? { 'X-Hermes-Session-Token': hermesToken()! } : undefined
    })
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
    promptUnreadSessionIds,
    markRunning,
    markFinished,
    isRunning,
    runIdForSession,
    markPromptUnread,
    clearPromptUnread,
    hasPromptUnread,
    trackRun,
    subscribe,
    stop,
    isRunFinished,
    onFinished
  }
}
