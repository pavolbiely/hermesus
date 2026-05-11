import type { AcpBridgeEvent } from '~/types/acp-api'
import type { AcpChatEvent, AcpTranscriptState } from '~/types/acp-chat'
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

  function applyBridgeEvent(event: AcpBridgeEvent) {
    normalizeAcpBridgeEvent(event).forEach(applyEvent)
  }

  return {
    state,
    messages,
    reset,
    applyEvent,
    applyBridgeEvent
  }
}
