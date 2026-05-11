import { ref } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import type { AcpChatMessage } from '../types/acp-chat'
import {
  acpMessageDurationDetails,
  acpMessageText,
  acpMessageTimestampDetails,
  acpTokenDetails,
  formatAcpMessageDuration,
  formatAcpMessageTimestamp,
  formatAcpTokenCount
} from '../utils/acpMessageMetadata'
import { hasTextParts } from '../utils/acpChatMessageDisplay'
import { writeClipboardText } from '../utils/clipboard'

export type MessageAction = {
  label: string
  icon: string
  kind?: 'default' | 'read-aloud'
  disabled?: boolean
  color?: 'neutral' | 'error'
  variant?: 'ghost'
  onClick: (event: MouseEvent, message: AcpChatMessageWithActions) => void | Promise<void>
}

export type AcpChatMessageWithActions = AcpChatMessage & {
  actions?: MessageAction[]
}

export type MessageMetadataItem = {
  key: string
  label: string
  title?: string
}

type ToastController = {
  add: (notification: { title: string, description?: string, color?: 'warning' | 'error' }) => unknown
}

type ReadAloudController = {
  speakingMessageId: Ref<string | null>
  generatingMessageId: Ref<string | null>
  isSupported: Ref<boolean> | ComputedRef<boolean>
  read: (message: AcpChatMessage) => void | Promise<void>
}

type MessageActionsOptions = {
  messages: ComputedRef<AcpChatMessage[]> | Ref<AcpChatMessage[]>
  activePromptTurnId: Ref<string | null>
  submitting: ComputedRef<boolean> | Ref<boolean>
  editingMessageId: Ref<string | null>
  readAloud: ReadAloudController
  toast: ToastController
  showError: (err: unknown, fallback: string) => void
  sendPrompt: (message: string) => Promise<unknown>
  startEditingUserMessage: (message: AcpChatMessage) => void | Promise<void>
}

export function useAcpMessageActions(options: MessageActionsOptions) {
  const hoveredAssistantMessageId = ref<string | null>(null)
  const focusedAssistantMessageId = ref<string | null>(null)

  function withNativeMessageActions(message: AcpChatMessage): AcpChatMessageWithActions {
    const text = acpMessageText(message).trim()
    if (
      message.role !== 'user'
      || !text
      || message.turnId === options.activePromptTurnId.value
      || options.editingMessageId.value === message.id
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
          disabled: options.submitting.value,
          onClick: () => options.startEditingUserMessage(message)
        }
      ]
    }
  }

  function assistantMessageActions(message: AcpChatMessage): MessageAction[] {
    const text = acpMessageText(message).trim()
    if (message.role !== 'assistant' || !text || message.turnId === options.activePromptTurnId.value) return []

    const isSpeaking = options.readAloud.speakingMessageId.value === message.id
    const isGeneratingSpeech = options.readAloud.generatingMessageId.value === message.id
    const isReadAloudActive = isSpeaking || isGeneratingSpeech
    return [
      {
        label: 'Regenerate response',
        icon: 'i-lucide-refresh-cw',
        disabled: options.submitting.value,
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
        disabled: !options.readAloud.isSupported.value,
        color: 'neutral',
        variant: 'ghost',
        onClick: () => options.readAloud.read(message)
      }
    ]
  }

  function isReadingAloud(message: AcpChatMessage) {
    return options.readAloud.speakingMessageId.value === message.id
  }

  function isGeneratingAloud(message: AcpChatMessage) {
    return options.readAloud.generatingMessageId.value === message.id
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

    const items: MessageMetadataItem[] = []
    if (message.createdAt) {
      items.push({
        key: 'time',
        label: formatAcpMessageTimestamp(message.createdAt),
        title: acpMessageTimestampDetails(message.createdAt)
      })
    }

    if (message.role === 'user') return items

    if (message.role !== 'assistant' || message.turnId === options.activePromptTurnId.value) return []

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
    if (options.submitting.value) return
    const prompt = previousUserPromptFor(message)
    if (!prompt) {
      options.toast.add({ color: 'warning', title: 'Could not find the prompt to regenerate.' })
      return
    }
    await options.sendPrompt(prompt)
  }

  function previousUserPromptFor(message: AcpChatMessage) {
    const source = options.messages.value
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
      options.toast.add({ title: 'Message copied' })
    } catch (err) {
      options.showError(err, 'Failed to copy message')
    }
  }

  return {
    hoveredAssistantMessageId,
    focusedAssistantMessageId,
    withNativeMessageActions,
    assistantMessageActions,
    isReadingAloud,
    isGeneratingAloud,
    readAloudStatusDetail,
    setAssistantMessageHover,
    onAssistantMessagePointerLeave,
    onAssistantMessageFocusOut,
    isAssistantFooterVisible,
    hasAssistantFooter,
    messageMetadataItems,
    regenerateResponse,
    previousUserPromptFor,
    copyMessageText
  }
}
