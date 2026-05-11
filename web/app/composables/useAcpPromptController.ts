import { nextTick, ref, type Ref } from 'vue'
import type {
  AcpListSessionsResponse,
  AvailableCommand,
  PlanEntry,
  RequestPermissionRequest,
  SessionConfigOption,
  SessionModeState,
  SessionModelState
} from '~/types/acp-api'
import type { AcpChatEvent, AcpChatMessage } from '~/types/acp-chat'
import type { ChatPromptAttachment } from '~/types/chat'
import type { QueuedMessage } from '~/utils/queuedMessages'
import { attachmentsToPromptBlocks } from '~/composables/useAcpPromptAttachments'
import type { useQueuedMessages } from '~/composables/useQueuedMessages'

type ChatSubmitStatus = 'ready' | 'submitted' | 'streaming'

type ToastApi = {
  add: (notification: { color: 'warning' | 'error', title: string, description?: string }) => unknown
}

type AcpPromptControllerOptions = {
  sessionId: Ref<string>
  input: Ref<string>
  loading: Ref<boolean>
  error: Ref<string | null>
  pendingPermissions: Ref<Array<{ appRequestId: string, request: RequestPermissionRequest }>>
  planEntries: Ref<PlanEntry[]>
  modelState: Ref<SessionModelState | null>
  modeState: Ref<SessionModeState | null>
  configOptions: Ref<SessionConfigOption[]>
  availableCommands: Ref<AvailableCommand[]>
  activePromptTurnId: Ref<string | null>
  submitStatusState: Ref<ChatSubmitStatus>
  submitting: Ref<boolean>
  submitStatus: Ref<ChatSubmitStatus>
  sidebarSessionsData: { data: Ref<AcpListSessionsResponse | null | undefined> }
  context: {
    attachments: Ref<ChatPromptAttachment[]>
    clearAttachments: () => void
  }
  api: {
    startPrompt: (sessionId: string, payload: {
      prompt: ReturnType<typeof attachmentsToPromptBlocks>
      turnId: string
      messageId: string
      replaceFromMessageId?: string
    }) => Promise<unknown>
    cancel: (sessionId: string) => Promise<unknown>
  }
  transcript: {
    state: Ref<{ cursor?: number, messages: AcpChatMessage[] }>
    applyEvent: (event: AcpChatEvent) => void
    appendLocalMessage: (message: AcpChatMessage) => void
    truncateFromMessage: (messageId: string) => void
    restoreMessages: (messages: AcpChatMessage[], cursor?: number) => void
  }
  queuedMessages: ReturnType<typeof useQueuedMessages>
  queuedForSession: Ref<QueuedMessage[]>
  activePrompts: {
    markFinished: (sessionId: string, turnId?: string | null) => void
  }
  clearDraft: () => void
  focusComposer: () => void
  scrollSubmittedMessageToBottom: (turnId: string) => void
  promoteSubmittedStatusToStreaming: (turnId: string) => void
  showError: (err: unknown, fallback: string) => void
  toast: ToastApi
}

export function useAcpPromptController(options: AcpPromptControllerOptions) {
  const steeringQueuedMessageId = ref<string | null>(null)
  const queuedMessageToSendAfterStop = ref<QueuedMessage | null>(null)
  const autoSendingQueuedMessage = ref(false)

  async function onSubmit() {
    const message = options.input.value.trim()
    if (!message && !options.context.attachments.value.length) return

    if (options.submitting.value) {
      enqueueMessage(message)
      return
    }

    const attachments = options.context.attachments.value
    options.clearDraft()
    options.context.clearAttachments()
    await sendPrompt(message, attachments)
  }

  function warnAttachmentsCannotBeQueued() {
    options.toast.add({
      color: 'warning',
      title: 'Attachments cannot be queued yet',
      description: 'Wait for the current response to finish, then send the message with attachments.'
    })
  }

  function enqueueMessage(message: string) {
    if (!message.trim()) return
    if (options.context.attachments.value.length) {
      warnAttachmentsCannotBeQueued()
      return
    }

    const queued = options.queuedMessages.enqueue(options.sessionId.value, message)
    if (queued) options.clearDraft()
  }

  function editQueuedMessage(id: string) {
    const queued = options.queuedForSession.value.find(message => message.id === id)
    if (!queued) return
    options.input.value = queued.text
    options.queuedMessages.remove(id)
    void nextTick(options.focusComposer)
  }

  function deleteQueuedMessage(id: string) {
    options.queuedMessages.remove(id)
  }

  async function steerQueuedMessage(id: string) {
    const queued = options.queuedForSession.value.find(message => message.id === id)
    if (!queued) return

    if (!options.submitting.value) {
      options.queuedMessages.remove(id)
      const sent = await sendPrompt(queued.text)
      if (!sent) options.queuedMessages.prepend(queued)
      return
    }

    steeringQueuedMessageId.value = id
    try {
      await options.api.cancel(options.sessionId.value)
      queuedMessageToSendAfterStop.value = queued
      options.queuedMessages.remove(id)
      options.activePrompts.markFinished(options.sessionId.value, options.activePromptTurnId.value)
      options.activePromptTurnId.value = null
      appendSteerMessage(queued.text)
    } catch (err) {
      options.showError(err, 'Failed to steer run')
    } finally {
      steeringQueuedMessageId.value = null
    }
  }

  function appendSteerMessage(text: string) {
    options.transcript.appendLocalMessage({
      id: `local-steer:${crypto.randomUUID()}`,
      role: 'system',
      sessionId: options.sessionId.value,
      createdAt: new Date().toISOString(),
      parts: [
        { type: 'event', title: 'Steer' },
        { type: 'text', text }
      ]
    })
  }

  async function sendNextQueuedMessage() {
    if (autoSendingQueuedMessage.value || options.loading.value || options.submitting.value) return

    const priority = queuedMessageToSendAfterStop.value?.sessionId === options.sessionId.value
      ? queuedMessageToSendAfterStop.value
      : null
    const queued = priority || options.queuedMessages.shiftForSession(options.sessionId.value)
    if (!queued) return
    if (priority) queuedMessageToSendAfterStop.value = null

    autoSendingQueuedMessage.value = true
    try {
      const sent = await sendPrompt(queued.text)
      if (!sent) options.queuedMessages.prepend(queued)
    } finally {
      autoSendingQueuedMessage.value = false
    }
  }

  function touchSidebarSession(targetSessionId: string, updatedAt = new Date().toISOString()) {
    const sidebarSessions = options.sidebarSessionsData.data.value?.sessions
    if (!sidebarSessions?.length) return

    let changed = false
    const sessions = sidebarSessions.map((session) => {
      if (session.sessionId !== targetSessionId) return session
      changed = true
      return { ...session, appUpdatedAt: updatedAt }
    })

    if (changed && options.sidebarSessionsData.data.value) {
      options.sidebarSessionsData.data.value = { ...options.sidebarSessionsData.data.value, sessions }
    }
  }

  async function sendPrompt(message: string, attachments: ChatPromptAttachment[] = [], promptOptions: { replaceFromMessageId?: string } = {}) {
    options.error.value = null
    const previousMessages = promptOptions.replaceFromMessageId
      ? options.transcript.state.value.messages.map(item => ({ ...item, parts: item.parts.map(part => ({ ...part })) }))
      : null
    const previousCursor = options.transcript.state.value.cursor
    const turnId = crypto.randomUUID()
    const messageId = crypto.randomUUID()
    const occurredAt = new Date().toISOString()
    if (promptOptions.replaceFromMessageId) options.transcript.truncateFromMessage(promptOptions.replaceFromMessageId)
    options.transcript.applyEvent({
      type: 'user.message',
      eventId: `optimistic-user:${turnId}`,
      sessionId: options.sessionId.value,
      turnId,
      messageId,
      text: message,
      occurredAt
    })
    touchSidebarSession(options.sessionId.value, occurredAt)
    options.activePromptTurnId.value = turnId
    options.submitStatusState.value = 'submitted'
    options.scrollSubmittedMessageToBottom(turnId)
    options.promoteSubmittedStatusToStreaming(turnId)

    try {
      await options.api.startPrompt(options.sessionId.value, {
        prompt: attachmentsToPromptBlocks(message || 'See attached files.', attachments),
        turnId,
        messageId,
        replaceFromMessageId: promptOptions.replaceFromMessageId
      })
      return true
    } catch (err) {
      if (previousMessages) {
        options.transcript.restoreMessages(previousMessages, previousCursor)
      }
      if (options.activePromptTurnId.value === turnId) options.activePromptTurnId.value = null
      options.activePrompts.markFinished(options.sessionId.value, turnId)
      options.showError(err, 'Failed to send prompt')
      return false
    }
  }

  async function stopPrompt() {
    if (!options.submitting.value) return
    try {
      await options.api.cancel(options.sessionId.value)
    } catch (err) {
      options.showError(err, 'Failed to cancel prompt')
    } finally {
      options.activePrompts.markFinished(options.sessionId.value, options.activePromptTurnId.value)
      options.activePromptTurnId.value = null
    }
  }

  return {
    steeringQueuedMessageId,
    queuedMessageToSendAfterStop,
    autoSendingQueuedMessage,
    onSubmit,
    enqueueMessage,
    editQueuedMessage,
    deleteQueuedMessage,
    steerQueuedMessage,
    sendNextQueuedMessage,
    sendPrompt,
    stopPrompt,
    touchSidebarSession
  }
}
