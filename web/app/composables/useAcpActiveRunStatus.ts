import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import type { AcpChatMessage } from '../types/acp-chat'

export type ChatSubmitStatus = 'ready' | 'submitted' | 'streaming'

type ActivePromptsStore = {
  markRunning: (sessionId: string, turnId: string) => void
  markFinished: (sessionId: string, turnId?: string | null) => void
}

type ActiveRunStatusOptions = {
  sessionId: ComputedRef<string> | Ref<string>
  messages: ComputedRef<AcpChatMessage[]> | Ref<AcpChatMessage[]>
  displayMessages: ComputedRef<AcpChatMessage[]> | Ref<AcpChatMessage[]>
  activePrompts: ActivePromptsStore
  hasRunDetails: (message: AcpChatMessage) => boolean
  getRunActivityLabel: (message: AcpChatMessage, activeTurnId: string | null) => string
  stillWorkingDelayMs?: number
}

export function useAcpActiveRunStatus(options: ActiveRunStatusOptions) {
  const activePromptTurnId = ref<string | null>(null)
  const activePromptSessionId = ref<string | null>(null)
  const activePromptStartedAt = ref<number | null>(null)
  const activePromptClockNow = ref(Date.now())
  const submitStatusState = ref<ChatSubmitStatus>('ready')
  let activePromptClockInterval: number | undefined

  const stillWorkingDelayMs = options.stillWorkingDelayMs ?? 10_000
  const submitting = computed(() => Boolean(activePromptTurnId.value))
  const submitStatus = computed(() => submitting.value ? submitStatusState.value : 'ready')
  const chatMessagesStatus = computed<ChatSubmitStatus>(() => submitStatus.value === 'submitted' ? 'streaming' : submitStatus.value)

  const activeRunMessage = computed(() => {
    if (!activePromptTurnId.value) return null
    return [...options.displayMessages.value].reverse().find(message => (
      message.turnId === activePromptTurnId.value
      && (message.role === 'assistant' || options.hasRunDetails(message))
    )) || null
  })

  const currentActivityLabel = computed(() => {
    const activeMessage = activeRunMessage.value
    if (!activePromptTurnId.value) return null
    if (!activeMessage) return fallbackActiveActivityLabel()
    return options.getRunActivityLabel(activeMessage, activePromptTurnId.value) || fallbackActiveActivityLabel()
  })

  const showRunActivityIndicator = computed(() => Boolean(currentActivityLabel.value))
  const currentActivityElapsedLabel = computed(() => {
    const startedAt = activePromptStartedAt.value
    if (!activePromptTurnId.value || !startedAt) return ''
    return formatElapsedDuration(activePromptClockNow.value - startedAt)
  })

  watch(activePromptTurnId, (turnId, previousTurnId) => {
    if (!turnId) {
      submitStatusState.value = 'ready'
      if (activePromptSessionId.value) {
        options.activePrompts.markFinished(activePromptSessionId.value, previousTurnId)
        activePromptSessionId.value = null
      }
      activePromptStartedAt.value = null
      stopActivePromptClock()
      return
    }

    if (submitStatusState.value === 'ready') submitStatusState.value = 'streaming'
    activePromptSessionId.value = options.sessionId.value
    options.activePrompts.markRunning(options.sessionId.value, turnId)
    activePromptStartedAt.value = activeTurnCreatedAtMs(turnId) ?? Date.now()
    startActivePromptClock()
  })

  onBeforeUnmount(stopActivePromptClock)

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
    const createdAt = options.messages.value.find(message => message.turnId === turnId)?.createdAt
    if (!createdAt) return null

    const time = Date.parse(createdAt)
    return Number.isFinite(time) ? time : null
  }

  function fallbackActiveActivityLabel() {
    const startedAt = activePromptStartedAt.value
    if (!startedAt) return 'Working…'
    return activePromptClockNow.value - startedAt >= stillWorkingDelayMs ? 'Still working…' : 'Working…'
  }

  return {
    activePromptTurnId,
    activePromptSessionId,
    activePromptStartedAt,
    activePromptClockNow,
    submitStatusState,
    submitting,
    submitStatus,
    chatMessagesStatus,
    activeRunMessage,
    currentActivityLabel,
    showRunActivityIndicator,
    currentActivityElapsedLabel,
    promoteSubmittedStatusToStreaming,
    startActivePromptClock,
    stopActivePromptClock,
    activeTurnCreatedAtMs,
    fallbackActiveActivityLabel
  }
}

export function formatElapsedDuration(milliseconds: number) {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1_000))
  if (totalSeconds < 60) return `${totalSeconds}s`

  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`
}
