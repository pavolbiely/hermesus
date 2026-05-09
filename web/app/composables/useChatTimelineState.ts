import { watch } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import type { SessionDetailResponse, WebChatMessage } from '~/types/web-chat'
import { mergeChatTimeline } from '~/utils/chatTimelineMerge'

type ActiveRunTracker = Pick<ReturnType<typeof useActiveChatRuns>, 'isRunning'>

type UseChatTimelineStateOptions = {
  sessionId: ComputedRef<string>
  displayedData: ComputedRef<SessionDetailResponse | null | undefined>
  messages: Ref<WebChatMessage[]>
  activeChatRuns: ActiveRunTracker
  onRenderedMessageCount?: (count: number) => void
}

export function useChatTimelineState(options: UseChatTimelineStateOptions) {
  let optimisticUserMessageIds = new Set<string>()
  let finalizedAssistantMessageIds = new Set<string>()

  function resetTimeline() {
    options.messages.value = []
    optimisticUserMessageIds = new Set()
    finalizedAssistantMessageIds = new Set()
    options.onRenderedMessageCount?.(0)
  }

  function reconcileSnapshot() {
    const currentSessionId = options.sessionId.value
    const loadedSessionId = options.displayedData.value?.session.id
    const persistedMessages = options.displayedData.value?.messages

    if (loadedSessionId !== currentSessionId) {
      resetTimeline()
      return
    }

    const activeRun = options.displayedData.value?.activeRun
    const preserveStreamingAssistant = Boolean(
      activeRun?.sessionId === currentSessionId
      || options.activeChatRuns.isRunning(currentSessionId)
    )

    const merged = mergeChatTimeline(
      persistedMessages ? [...persistedMessages] : [],
      options.messages.value,
      optimisticUserMessageIds,
      {
        preserveStreamingAssistant,
        preserveAssistantMessageIds: finalizedAssistantMessageIds
      }
    )

    options.messages.value = merged.messages
    optimisticUserMessageIds = merged.optimisticMessageIds
    finalizedAssistantMessageIds = merged.preservedAssistantMessageIds
    options.onRenderedMessageCount?.(merged.messages.length)
  }

  function addOptimisticUserMessage(message: WebChatMessage) {
    optimisticUserMessageIds.add(message.id)
    options.messages.value.push(message)
    options.onRenderedMessageCount?.(options.messages.value.length)
  }

  function canonicalizeUserMessage(localMessageId: string, canonicalMessageId: string) {
    optimisticUserMessageIds.delete(localMessageId)
    optimisticUserMessageIds.add(canonicalMessageId)
  }

  function removeOptimisticUserMessage(messageId: string) {
    optimisticUserMessageIds.delete(messageId)
  }

  function markAssistantFinalized(message: WebChatMessage) {
    finalizedAssistantMessageIds.add(message.id)
  }

  watch(
    [
      options.sessionId,
      () => options.displayedData.value?.session.id,
      () => options.displayedData.value?.messages,
      () => options.displayedData.value?.activeRun
    ],
    reconcileSnapshot,
    { immediate: true }
  )

  return {
    addOptimisticUserMessage,
    canonicalizeUserMessage,
    removeOptimisticUserMessage,
    markAssistantFinalized,
    resetTimeline,
    reconcileSnapshot
  }
}
