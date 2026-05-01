import type { ComputedRef, Ref } from 'vue'
import type { AgentStatusEvent, InteractivePrompt, WebChatMessage, WebChatPart, WebChatSystemEventSeverity, WebChatSystemEventType, WebChatTaskPlan, WebChatWorkspaceChanges } from '~/types/web-chat'
import { applyRunMetrics, inputTokenCount, latestTaskPlanFromMessages, type RunMetrics } from '~/utils/chatRunMessages'
import { toolDisplayName, toolRawName } from '~/utils/toolCalls'
import { createLocalMessage } from './useHermesRunStream'

type SubmitStatus = 'ready' | 'submitted' | 'streaming' | 'error'
type RunActivityKind = 'starting' | 'thinking' | 'tool' | 'composing' | 'working'

type RunActivity = {
  label: string
  kind: RunActivityKind
  updatedAt: number
}

type SystemEventOptions = {
  eventType: WebChatSystemEventType
  severity?: WebChatSystemEventSeverity
  title: string
  description?: string | null
  text?: string | null
  occurredAt?: string | null
  metadata?: Record<string, unknown> | null
  messageId?: string | null
  dedupeKey?: string | null
}

const STILL_WORKING_DELAY_MS = 8000

type UseChatRunMessagesOptions = {
  sessionId: ComputedRef<string>
  refresh: () => Promise<unknown> | unknown
  refreshSessions?: () => Promise<void> | void
  refreshSessionOnFinish?: boolean
  toast: ReturnType<typeof useToast>
  activeChatRuns: ReturnType<typeof useActiveChatRuns>
}

export function useChatRunMessages(options: UseChatRunMessagesOptions) {
  const messages = ref<WebChatMessage[]>([])
  const submitStatus: Ref<SubmitStatus> = ref('ready')
  const streamError = ref<Error | undefined>()
  const hasAssistantResponseStarted = ref(false)
  const currentActivity = ref<RunActivity | null>(null)
  const now = ref(Date.now())
  const connectedRunIds = new Set<string>()
  const systemEventKeys = new Set<string>()
  let unsubscribeRun: (() => void) | undefined
  let activityTimer: ReturnType<typeof setInterval> | undefined

  const isRunning = computed(() => options.activeChatRuns.isRunning(options.sessionId.value))
  const currentActivityLabel = computed(() => {
    if (!isRunning.value && submitStatus.value !== 'submitted') return null

    const activity = currentActivity.value
    if (!activity) return submitStatus.value === 'submitted' ? 'Starting…' : 'Working…'
    if (activity.kind !== 'tool' && now.value - activity.updatedAt > STILL_WORKING_DELAY_MS) return 'Still working…'
    return activity.label
  })
  const chatStatus = computed(() => {
    if (submitStatus.value === 'error') return 'error'
    if (submitStatus.value === 'submitted' || (isRunning.value && !hasAssistantResponseStarted.value)) return 'submitted'
    return isRunning.value ? 'streaming' : 'ready'
  })
  const latestTaskPlan = computed(() => latestTaskPlanFromMessages(messages.value))

  function setActivity(label: string, kind: RunActivityKind) {
    currentActivity.value = { label, kind, updatedAt: Date.now() }
    now.value = Date.now()
  }

  function clearActivity() {
    currentActivity.value = null
  }

  function ensureActivityTimer() {
    if (activityTimer || typeof setInterval !== 'function') return
    activityTimer = setInterval(() => {
      now.value = Date.now()
    }, 1000)
  }

  function assistantMessage() {
    let assistant = messages.value[messages.value.length - 1]
    if (!assistant || assistant.role !== 'assistant') {
      assistant = createLocalMessage('assistant', '')
      messages.value.push(assistant)
    }
    return assistant
  }

  function removeThinkingPart(message: WebChatMessage) {
    const thinkingIndex = message.parts.findIndex(part => part.status === 'thinking')
    if (thinkingIndex >= 0) message.parts.splice(thinkingIndex, 1)
  }

  function appendAssistantDelta(content: string) {
    if (!content) return

    setActivity('Composing response…', 'composing')
    hasAssistantResponseStarted.value = true
    const assistant = assistantMessage()
    removeThinkingPart(assistant)
    completeOpenReasoning(assistant)

    const textPart = assistant.parts.find(part => part.type === 'text')
    if (textPart) {
      textPart.text = `${textPart.text || ''}${content}`
      textPart.status = null
    } else {
      assistant.parts.push({ type: 'text', text: content })
    }

  }

  function appendCompletedChanges(changes?: WebChatWorkspaceChanges | null) {
    if (!changes?.files?.length) return

    const assistant = assistantMessage()
    const existing = assistant.parts.find(part => part.type === 'changes')
    if (existing) {
      existing.changes = changes
    } else {
      assistant.parts.push({ type: 'changes', changes })
    }
  }

  function applyRunMetricsToLatestUser(payload: RunMetrics) {
    const user = [...messages.value].reverse().find(message => message.role === 'user')
    if (!user) return

    applyRunMetrics(user, {
      ...payload,
      tokenCount: inputTokenCount(payload)
    })
  }

  function replaceAssistantMessage(payload: { content?: string, changes?: WebChatWorkspaceChanges | null } & RunMetrics) {
    if (!payload.content && !payload.changes?.files?.length) return

    setActivity('Finalizing…', 'working')
    hasAssistantResponseStarted.value = true
    applyRunMetricsToLatestUser(payload)
    const assistant = assistantMessage()
    removeThinkingPart(assistant)
    applyRunMetrics(assistant, payload)
    const completedAt = new Date().toISOString()
    for (const part of assistant.parts) {
      if (part.type === 'reasoning' && part.status === 'streaming') {
        part.status = null
        completeProcessPart(part, completedAt)
      }
      if (part.type === 'tool' && part.status === 'running') {
        part.status = 'completed'
        completeProcessPart(part, completedAt)
      }
    }
    if (payload.content) {
      const textPart = assistant.parts.find(part => part.type === 'text')
      if (textPart) {
        textPart.text = payload.content
        textPart.status = null
      } else {
        assistant.parts.push({ type: 'text', text: payload.content, status: null })
      }
    }
    appendCompletedChanges(payload.changes)
  }

  function completeProcessPart(part: WebChatPart, completedAt = new Date().toISOString()) {
    if (part.completedAt) return
    part.completedAt = completedAt
    const startedAt = part.startedAt ? new Date(part.startedAt).getTime() : null
    const endedAt = new Date(completedAt).getTime()
    if (startedAt && Number.isFinite(startedAt) && Number.isFinite(endedAt)) {
      part.durationMs = Math.max(0, endedAt - startedAt)
    }
  }

  function completeOpenReasoning(message: WebChatMessage) {
    const reasoningPart = message.parts.findLast(part => part.type === 'reasoning' && part.status === 'streaming')
    if (!reasoningPart) return
    reasoningPart.status = null
    completeProcessPart(reasoningPart)
  }

  function appendSystemEvent(event: SystemEventOptions) {
    const key = event.dedupeKey || `${event.messageId || event.eventType}:${event.title}:${event.description || event.text || ''}`
    if (systemEventKeys.has(key)) return
    if (event.messageId && messages.value.some(message => message.id === event.messageId)) return
    systemEventKeys.add(key)

    const localMessage = createLocalMessage('system', '')
    messages.value.push({
      ...localMessage,
      id: event.messageId || localMessage.id,
      createdAt: event.occurredAt || new Date().toISOString(),
      parts: [{
        type: 'event',
        eventType: event.eventType,
        severity: event.severity || 'info',
        title: event.title,
        description: event.description,
        text: event.text,
        occurredAt: event.occurredAt || null,
        metadata: event.metadata || null
      }]
    })
  }

  function appendReasoningDelta(content: string) {
    if (!content) return

    setActivity('Thinking…', 'thinking')
    hasAssistantResponseStarted.value = true
    const assistant = assistantMessage()
    removeThinkingPart(assistant)

    const lastPart = assistant.parts.at(-1)
    if (lastPart?.type === 'reasoning') {
      lastPart.text = `${lastPart.text || ''}${content}`
    } else {
      assistant.parts.push({ type: 'reasoning', text: content, status: 'streaming', startedAt: new Date().toISOString() })
    }
  }

  function appendToolStarted(payload: { name?: string, preview?: string, input?: unknown, occurredAt?: string }) {
    const toolPart: WebChatPart = {
      type: 'tool',
      name: payload.name,
      status: 'running',
      startedAt: payload.occurredAt || new Date().toISOString(),
      input: payload.input ?? payload.preview ?? null
    }
    toolPart.name = toolRawName(toolPart)
    setActivity(`Running ${toolDisplayName(toolPart)}…`, 'tool')
    hasAssistantResponseStarted.value = true
    let assistant = messages.value[messages.value.length - 1]
    if (!assistant || assistant.role !== 'assistant') {
      assistant = createLocalMessage('assistant', '')
      messages.value.push(assistant)
    }

    const thinkingIndex = assistant.parts.findIndex(part => part.status === 'thinking')
    if (thinkingIndex >= 0) assistant.parts.splice(thinkingIndex, 1)
    completeOpenReasoning(assistant)

    assistant.parts.push(toolPart)
  }

  function appendStatus(payload: AgentStatusEvent) {
    setActivity(payload.kind === 'warn' ? 'Checking results…' : 'Working…', 'working')
    if (payload.kind === 'warn') {
      appendSystemEvent({
        eventType: 'agent_warning',
        severity: 'warning',
        title: 'Agent warning',
        description: payload.message,
        occurredAt: payload.createdAt,
        messageId: payload.messageId,
        dedupeKey: `agent_warning:${payload.messageId || payload.createdAt || payload.message}`
      })
      return
    }

    hasAssistantResponseStarted.value = true
    const assistant = assistantMessage()
    removeThinkingPart(assistant)
    completeOpenReasoning(assistant)
    assistant.parts.push({ type: 'status', text: payload.message, status: payload.kind })
  }

  function appendTaskPlan(taskPlan: WebChatTaskPlan) {
    if (!taskPlan.items.length) return

    setActivity('Updating plan…', 'working')
    hasAssistantResponseStarted.value = true
    const assistant = assistantMessage()
    removeThinkingPart(assistant)
    completeOpenReasoning(assistant)

    const existing = assistant.parts.find(part => part.type === 'task_plan')
    if (existing) {
      existing.taskPlan = taskPlan
      return
    }

    assistant.parts.push({ type: 'task_plan', taskPlan })
  }

  function markToolCompleted(payload: { name?: string, occurredAt?: string }) {
    setActivity('Thinking…', 'thinking')
    const assistant = [...messages.value].reverse().find(message => message.role === 'assistant')
    const displayName = payload.name ? toolDisplayName({ name: payload.name }) : null
    const rawName = payload.name ? toolRawName({ name: payload.name }) : null
    const toolPart = assistant?.parts.findLast(part => part.type === 'tool' && part.status === 'running' && (!payload.name || part.name === payload.name || part.name === rawName || part.name === displayName))
    if (toolPart) {
      toolPart.status = 'completed'
      completeProcessPart(toolPart, payload.occurredAt || new Date().toISOString())
    }
  }

  function appendPrompt(prompt: InteractivePrompt) {
    hasAssistantResponseStarted.value = true
    const assistant = assistantMessage()
    removeThinkingPart(assistant)
    const existing = assistant.parts.find(part => part.prompt?.id === prompt.id)
    if (existing) {
      existing.prompt = prompt
      return
    }
    assistant.parts.push({ type: 'interactive_prompt', prompt })
  }

  function updatePrompt(prompt: InteractivePrompt) {
    for (const message of messages.value) {
      const part = message.parts.find(part => part.prompt?.id === prompt.id)
      if (part) {
        part.prompt = prompt
        return
      }
    }
  }

  function appendPromptExpired(prompt: InteractivePrompt) {
    appendSystemEvent({
      eventType: 'prompt_expired',
      severity: 'warning',
      title: prompt.kind === 'approval' ? 'Approval expired' : 'Question expired',
      description: prompt.title,
      occurredAt: prompt.answeredAt || new Date().toISOString(),
      dedupeKey: `prompt_expired:${prompt.id}`
    })
  }

  function appendPromptCancelled(prompt: InteractivePrompt) {
    appendSystemEvent({
      eventType: 'prompt_cancelled',
      title: prompt.kind === 'approval' ? 'Approval cancelled' : 'Question cancelled',
      description: prompt.title,
      occurredAt: prompt.answeredAt || new Date().toISOString(),
      dedupeKey: `prompt_cancelled:${prompt.id}`
    })
  }

  function connectRun(runId: string, targetSessionId = options.sessionId.value) {
    if (targetSessionId === options.sessionId.value) hasAssistantResponseStarted.value = false
    const tracked = options.activeChatRuns.trackRun(targetSessionId, runId)
    if (!tracked) {
      connectedRunIds.delete(runId)
      submitStatus.value = 'ready'
      void options.refresh()
      void options.refreshSessions?.()
      return
    }
    connectedRunIds.add(runId)

    if (targetSessionId === options.sessionId.value) {
      submitStatus.value = 'streaming'
      setActivity('Starting…', 'starting')
      ensureActivityTimer()
    }

    unsubscribeRun?.()
    unsubscribeRun = options.activeChatRuns.subscribe(targetSessionId, {
      onDelta: (content) => {
        if (targetSessionId === options.sessionId.value) appendAssistantDelta(content)
      },
      onReasoningDelta: (content) => {
        if (targetSessionId === options.sessionId.value) appendReasoningDelta(content)
      },
      onCompleted: (payload) => {
        if (targetSessionId !== options.sessionId.value) return
        replaceAssistantMessage(payload)
      },
      onToolStarted: (payload) => {
        if (targetSessionId === options.sessionId.value) appendToolStarted(payload)
      },
      onToolCompleted: (payload) => {
        if (targetSessionId === options.sessionId.value) markToolCompleted(payload)
      },
      onTaskPlanUpdated: (taskPlan) => {
        if (targetSessionId === options.sessionId.value) appendTaskPlan(taskPlan)
      },
      onStatus: (payload) => {
        if (targetSessionId === options.sessionId.value) appendStatus(payload)
      },
      onPromptRequested: (prompt) => {
        if (targetSessionId === options.sessionId.value) appendPrompt(prompt)
      },
      onPromptUpdated: (prompt) => {
        if (targetSessionId === options.sessionId.value) updatePrompt(prompt)
      },
      onPromptExpired: (prompt) => {
        if (targetSessionId === options.sessionId.value) appendPromptExpired(prompt)
      },
      onPromptCancelled: (prompt) => {
        if (targetSessionId === options.sessionId.value) appendPromptCancelled(prompt)
      },
      onRunStopped: (payload) => {
        if (targetSessionId !== options.sessionId.value) return
        appendSystemEvent({
          eventType: 'run_stopped',
          title: 'Run stopped',
          description: payload.message || 'Stopped by user.',
          occurredAt: payload.occurredAt,
          messageId: payload.messageId,
          dedupeKey: `run_stopped:${payload.messageId || runId}`
        })
      },
      onRunFailed: (payload) => {
        if (targetSessionId !== options.sessionId.value) return
        appendSystemEvent({
          eventType: 'run_failed',
          severity: 'error',
          title: 'Run failed',
          description: payload.error,
          occurredAt: payload.occurredAt,
          messageId: payload.messageId,
          dedupeKey: `run_failed:${payload.messageId || runId}`
        })
      },
      onRunSteered: (payload) => {
        if (targetSessionId !== options.sessionId.value) return
        appendSystemEvent({
          eventType: 'run_steered',
          title: 'Run steered',
          description: payload.text || null,
          occurredAt: payload.occurredAt,
          messageId: payload.messageId,
          dedupeKey: `run_steered:${payload.messageId || payload.text || runId}`
        })
      },
      onError: (err) => {
        if (targetSessionId !== options.sessionId.value) return
        streamError.value = err
        submitStatus.value = 'error'
        options.toast.add({ color: 'error', title: 'Run failed', description: err.message })
      },
      async onFinished() {
        if (targetSessionId === options.sessionId.value) {
          submitStatus.value = 'ready'
          clearActivity()
          if (options.refreshSessionOnFinish !== false) {
            await options.refresh()
          }
        }
        await options.refreshSessions?.()
      }
    })
  }

  function hasConnectedRun(runId: string) {
    return connectedRunIds.has(runId)
  }

  function cleanupRunMessages() {
    unsubscribeRun?.()
    if (activityTimer) clearInterval(activityTimer)
    activityTimer = undefined
  }

  return {
    messages,
    submitStatus,
    streamError,
    chatStatus,
    currentActivityLabel,
    latestTaskPlan,
    isRunning,
    connectRun,
    hasConnectedRun,
    cleanupRunMessages
  }
}
