import { nextTick, ref } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import { prepareNotificationSound } from '~/utils/notificationSound'
import type { SessionDetailResponse, WebChatMessage } from '~/types/web-chat'
import { messageText } from '~/utils/chatMessages'

type UseChatMessageEditingOptions = {
  api: ReturnType<typeof useHermesApi>
  data: Ref<SessionDetailResponse | null | undefined>
  messages: Ref<WebChatMessage[]>
  sessionId: ComputedRef<string>
  submitStatus: Ref<'ready' | 'submitted' | 'streaming' | 'error'>
  autoScrollEnabled: Ref<boolean>
  selectedWorkspace: Ref<string | null>
  selectedModel: Ref<string | null>
  selectedReasoningEffort: Ref<string | null>
  activeChatRuns: ReturnType<typeof useActiveChatRuns>
  createThinkingMessage: () => WebChatMessage
  scheduleAutoScroll: () => void
  connectRun: (runId: string, sessionId: string) => void
  rememberLastUsedSelection: () => void
  showError: (err: unknown, fallback: string) => void
}

export function useChatMessageEditing(options: UseChatMessageEditingOptions) {
  const editingMessageId = ref<string | null>(null)
  const editingText = ref('')
  const editingMessageContainer = ref<HTMLElement | null>(null)
  const editingMessageBubble = ref<HTMLElement | null>(null)
  const editingMessageRow = ref<HTMLElement | null>(null)
  const savingEditedMessageId = ref<string | null>(null)

  function setEditingMessageContainer(el: unknown) {
    editingMessageContainer.value = el instanceof HTMLElement ? el : null
  }

  function resetEditingTextareaLayout() {
    if (editingMessageContainer.value) {
      editingMessageContainer.value.style.width = ''
      editingMessageContainer.value.style.marginLeft = ''
    }

    if (editingMessageBubble.value) {
      editingMessageBubble.value.style.width = ''
      editingMessageBubble.value = null
    }

    if (editingMessageRow.value) {
      editingMessageRow.value.style.width = ''
      editingMessageRow.value.style.maxWidth = ''
      editingMessageRow.value.style.transform = ''
      editingMessageRow.value = null
    }
  }

  function alignEditingTextareaWithPrompt() {
    const container = editingMessageContainer.value
    const promptTextarea = document.querySelector<HTMLTextAreaElement>('textarea[placeholder="Type your message here…"]')
    const promptRoot = promptTextarea?.closest<HTMLElement>('[data-slot="root"]')
    const bubble = container?.parentElement
    const row = bubble?.parentElement
    if (!container || !promptRoot || !bubble || !row) return

    const promptRect = promptRoot.getBoundingClientRect()
    const bubbleStyle = getComputedStyle(bubble)
    const bubblePaddingLeft = parseFloat(bubbleStyle.paddingLeft) || 0
    const bubblePadding = bubblePaddingLeft + (parseFloat(bubbleStyle.paddingRight) || 0)
    const bubbleWidth = promptRect.width + bubblePadding

    editingMessageBubble.value = bubble
    editingMessageRow.value = row
    row.style.width = `${bubbleWidth}px`
    row.style.maxWidth = 'none'
    row.style.transform = `translateX(-${bubblePaddingLeft}px)`
    bubble.style.width = `${bubbleWidth}px`
    container.style.width = `${promptRect.width}px`
    container.style.marginLeft = '0'
  }

  async function focusEditingTextarea() {
    await nextTick()
    alignEditingTextareaWithPrompt()
    const textarea = editingMessageContainer.value?.querySelector('textarea')
    if (!textarea) return
    textarea.focus()
    const end = textarea.value.length
    textarea.setSelectionRange(end, end)
  }

  function startEditingMessage(message: WebChatMessage) {
    if (options.activeChatRuns.isRunning(options.sessionId.value) || options.submitStatus.value === 'submitted') return
    resetEditingTextareaLayout()
    editingMessageId.value = message.id
    editingText.value = messageText(message)
    void focusEditingTextarea()
  }

  function cancelEditingMessage() {
    resetEditingTextareaLayout()
    editingMessageId.value = null
    editingText.value = ''
  }

  function messageAttachmentIds(message: WebChatMessage) {
    return message.parts
      .flatMap(part => part.type === 'media' ? part.attachments || [] : [])
      .map(attachment => attachment.id)
  }

  async function saveEditedMessage(message: WebChatMessage) {
    const content = editingText.value.trim()
    if (!content || savingEditedMessageId.value || options.activeChatRuns.isRunning(options.sessionId.value)) return

    const previousMessages = [...options.messages.value]
    savingEditedMessageId.value = message.id
    void prepareNotificationSound()

    try {
      const updated = await options.api.editMessage(options.sessionId.value, message.id, content)
      options.data.value = updated
      options.messages.value = [...updated.messages]
      resetEditingTextareaLayout()
      editingMessageId.value = null
      editingText.value = ''
      options.submitStatus.value = 'submitted'
      options.autoScrollEnabled.value = true
      options.messages.value.push(options.createThinkingMessage())
      options.scheduleAutoScroll()

      const attachmentIds = messageAttachmentIds(message)
      const run = await options.api.startRun(content, {
        sessionId: options.sessionId.value,
        model: options.selectedModel.value,
        reasoningEffort: options.selectedReasoningEffort.value,
        workspace: options.selectedWorkspace.value || undefined,
        attachments: attachmentIds,
        editedMessageId: message.id
      })
      options.rememberLastUsedSelection()
      options.connectRun(run.runId, options.sessionId.value)
    } catch (err) {
      options.messages.value = previousMessages
      options.submitStatus.value = 'error'
      options.activeChatRuns.markFinished(options.sessionId.value)
      options.showError(err, 'Failed to edit message')
    } finally {
      savingEditedMessageId.value = null
    }
  }

  return {
    editingMessageId,
    editingText,
    savingEditedMessageId,
    setEditingMessageContainer,
    resetEditingTextareaLayout,
    startEditingMessage,
    cancelEditingMessage,
    saveEditedMessage
  }
}
