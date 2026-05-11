import type { AcpBridgeEvent } from '~/types/acp-api'
import type { AcpChatEvent, AcpChatMessage, AcpTranscriptState } from '~/types/acp-chat'
import { applyAcpChatEvent, createEmptyAcpTranscriptState } from '~/utils/acpEventNormalization'
import { normalizeAcpBridgeEvent } from '~/utils/acpBridgeEventNormalization'

export function useAcpTranscript() {
  const state = ref<AcpTranscriptState>(createEmptyAcpTranscriptState())

  const messages = computed(() => state.value.messages)

  function reset() {
    state.value = createEmptyAcpTranscriptState()
  }

  function applyEvent(event: AcpChatEvent) {
    state.value = applyAcpChatEvent(state.value, event)
  }

  function restoreMessages(messages: AcpChatMessage[], cursor = state.value.cursor) {
    applyEvent({
      type: 'transcript.loaded',
      sessionId: messages[messages.length - 1]?.sessionId || '',
      cursor,
      messages
    })
  }

  function prependMessages(messages: AcpChatMessage[]) {
    const existingIds = new Set(state.value.messages.map(message => message.id))
    state.value = {
      ...state.value,
      messages: [
        ...messages.filter(message => !existingIds.has(message.id)),
        ...state.value.messages
      ]
    }
  }

  function appendLocalMessage(message: AcpChatMessage) {
    if (state.value.messages.some(item => item.id === message.id)) return
    state.value = {
      ...state.value,
      messages: [...state.value.messages, message]
    }
  }

  function truncateFromMessage(messageId: string) {
    const sessionId = state.value.messages.find(message => message.id === messageId)?.sessionId || ''
    applyEvent({ type: 'transcript.truncated', sessionId, messageId })
  }

  function applyBridgeEvent(event: AcpBridgeEvent) {
    normalizeAcpBridgeEvent(event).forEach(applyEvent)
  }

  return {
    state,
    messages,
    reset,
    restoreMessages,
    prependMessages,
    truncateFromMessage,
    appendLocalMessage,
    applyEvent,
    applyBridgeEvent
  }
}
