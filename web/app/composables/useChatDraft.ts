import { computed, onBeforeUnmount, ref, toValue, watch } from 'vue'
import type { MaybeRefOrGetter } from 'vue'
import { readChatDraft, writeChatDraft } from '~/utils/chatDrafts'

function draftStorage() {
  return import.meta.client ? window.localStorage : undefined
}

export function useChatDraft(draftId: MaybeRefOrGetter<string>) {
  const currentDraftId = computed(() => toValue(draftId))
  const input = ref('')

  watch(
    currentDraftId,
    (nextDraftId, previousDraftId) => {
      if (previousDraftId) writeChatDraft(draftStorage(), previousDraftId, input.value)
      input.value = readChatDraft(draftStorage(), nextDraftId)
    },
    { immediate: true, flush: 'sync' }
  )

  watch(input, (text) => {
    writeChatDraft(draftStorage(), currentDraftId.value, text)
  })

  onBeforeUnmount(() => {
    writeChatDraft(draftStorage(), currentDraftId.value, input.value)
  })

  function clearDraft() {
    input.value = ''
    writeChatDraft(draftStorage(), currentDraftId.value, '')
  }

  return {
    input,
    clearDraft
  }
}
