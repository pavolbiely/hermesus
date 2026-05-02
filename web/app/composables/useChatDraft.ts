import { computed, onBeforeUnmount, ref, toValue, watch } from 'vue'
import type { MaybeRefOrGetter } from 'vue'
import { readChatDraft, writeChatDraft } from '~/utils/chatDrafts'

function draftStorage() {
  return import.meta.client ? window.localStorage : undefined
}

export function useChatDraft(draftId: MaybeRefOrGetter<string>) {
  const currentDraftId = computed(() => toValue(draftId))
  const draftMemory = useState<Record<string, string>>('web-chat-draft-memory', () => ({}))
  const input = ref('')

  function readDraft(draftId: string) {
    return draftMemory.value[draftId] ?? readChatDraft(draftStorage(), draftId)
  }

  function writeDraft(draftId: string, text: string) {
    if (text) draftMemory.value[draftId] = text
    else delete draftMemory.value[draftId]
    writeChatDraft(draftStorage(), draftId, text)
  }

  watch(
    currentDraftId,
    (nextDraftId, previousDraftId) => {
      if (previousDraftId) writeDraft(previousDraftId, input.value)
      input.value = readDraft(nextDraftId)
    },
    { immediate: true, flush: 'sync' }
  )

  watch(input, (text) => {
    writeDraft(currentDraftId.value, text)
  }, { flush: 'sync' })

  onBeforeUnmount(() => {
    writeDraft(currentDraftId.value, input.value)
  })

  function clearDraft() {
    input.value = ''
    writeDraft(currentDraftId.value, '')
  }

  return {
    input,
    clearDraft
  }
}
