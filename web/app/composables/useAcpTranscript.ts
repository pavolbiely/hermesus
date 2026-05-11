import type { AcpBridgeEvent, AcpTranscriptSnapshot } from '~/types/acp-api'
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

  function loadSnapshot(snapshot: AcpTranscriptSnapshot) {
    applyEvent({
      type: 'transcript.loaded',
      sessionId: snapshot.sessionId,
      cursor: snapshot.cursor,
      messages: snapshot.messages
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

  function applyBridgeEvent(event: AcpBridgeEvent) {
    normalizeAcpBridgeEvent(event).forEach(applyEvent)
  }

  return {
    state,
    messages,
    reset,
    loadSnapshot,
    prependMessages,
    applyEvent,
    applyBridgeEvent
  }
}
