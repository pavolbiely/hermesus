import { nextTick, ref } from 'vue'
import type { ComputedRef } from 'vue'
import type { AcpChatMessage } from '../types/acp-chat'
import type { ChatPromptAttachment } from '../types/chat'
import { acpMessageText } from '../utils/acpMessageMetadata'

type MessageEditingOptions = {
  submitting: ComputedRef<boolean>
  sendPrompt: (message: string, attachments?: ChatPromptAttachment[], options?: { replaceFromMessageId?: string }) => Promise<unknown>
}

export function useAcpMessageEditing(options: MessageEditingOptions) {
  const editingMessageId = ref<string | null>(null)
  const editingText = ref('')
  const editingMessageContainer = ref<HTMLElement | null>(null)
  const savingEditedMessageId = ref<string | null>(null)

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
    if (!text || options.submitting.value) return

    editingMessageId.value = message.id
    editingText.value = text
    await focusEditingTextarea()
  }

  async function saveEditedUserMessage(message: AcpChatMessage) {
    const text = editingText.value.trim()
    if (!text || options.submitting.value || savingEditedMessageId.value) return

    const previousText = acpMessageText(message).trim()
    if (text === previousText) {
      cancelEditingUserMessage()
      return
    }

    savingEditedMessageId.value = message.id
    try {
      cancelEditingUserMessage()
      await options.sendPrompt(text, [], { replaceFromMessageId: message.id })
    } finally {
      savingEditedMessageId.value = null
    }
  }

  return {
    editingMessageId,
    editingText,
    editingMessageContainer,
    savingEditedMessageId,
    setEditingMessageContainer,
    cancelEditingUserMessage,
    focusEditingTextarea,
    startEditingUserMessage,
    saveEditedUserMessage
  }
}
