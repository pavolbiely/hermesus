<script setup lang="ts">
import type { WebChatMessage } from '~/types/web-chat'
import {
  formatMessageGenerationDuration,
  formatMessageTimestamp,
  formatMessageTokenCount,
  messageDurationDetails,
  messageTimestampTitle,
  messageTokenDetails,
  messageTokenTooltipNote
} from '~/utils/chatMessages'

const props = defineProps<{
  message: WebChatMessage
  copiedMessageId: string | null
  savingEditedMessageId: string | null
  isRunning: boolean
}>()

const emit = defineEmits<{
  copy: [message: WebChatMessage]
  regenerate: [message: WebChatMessage]
  edit: [message: WebChatMessage]
}>()

const openTooltipKey = ref<string | null>(null)
const tooltipContent = { side: 'top' as const, sideOffset: 8 }
const richTooltipUi = {
  content: 'h-auto max-w-none items-stretch rounded-md bg-elevated px-3 py-2 text-default shadow-lg ring ring-default'
}

const { generatingMessageId, playbackCacheStatuses, playbackSources, speakingMessageId, read: readAloud, stop: stopReadAloud } = useMessageReadAloud()

const tokenCount = computed(() => props.message.role === 'assistant' ? formatMessageTokenCount(props.message) : '')
const generationDuration = computed(() => props.message.role === 'assistant' ? formatMessageGenerationDuration(props.message) : '')
const isReadingAloud = computed(() => speakingMessageId.value === props.message.id)
const isGeneratingAloud = computed(() => generatingMessageId.value === props.message.id)
const isReadAloudActive = computed(() => isReadingAloud.value || isGeneratingAloud.value)
const readAloudPlaybackSource = computed(() => playbackSources.value[props.message.id] ?? null)
const readAloudCacheStatus = computed(() => playbackCacheStatuses.value[props.message.id] ?? null)
const readAloudStatusText = computed(() => {
  if (isGeneratingAloud.value) {
    if (readAloudPlaybackSource.value === 'readable-summary') return 'Preparing readable summary'
    if (readAloudPlaybackSource.value === 'edge-tts-fallback-generating') return 'Generating Edge TTS fallback audio'
    return 'Generating speech audio'
  }

  if (isReadingAloud.value) {
    if (readAloudPlaybackSource.value === 'web-speech') return 'Reading via Browser Web Speech API'
    if (readAloudPlaybackSource.value === 'edge-tts-stream') return 'Reading via Edge TTS stream'
    if (readAloudPlaybackSource.value === 'edge-tts-fallback-blob') return 'Reading via Edge TTS fallback audio'
    return 'Reading aloud'
  }

  return ''
})
const readAloudStatusDetail = computed(() => {
  if (!readAloudStatusText.value) return ''
  if (!readAloudCacheStatus.value) return readAloudStatusText.value
  const cacheLabel = readAloudCacheStatus.value === 'cached' ? 'cached' : 'not cached'
  return `${readAloudStatusText.value} (${cacheLabel})`
})
const readAloudAriaLabel = computed(() => {
  if (isGeneratingAloud.value) return 'Stop generating speech audio'
  return isReadingAloud.value ? 'Stop reading message aloud' : 'Read message aloud'
})

function setTooltipOpen(key: string, open: boolean) {
  if (open) {
    openTooltipKey.value = key
  } else if (openTooltipKey.value === key) {
    openTooltipKey.value = null
  }
}

onBeforeUnmount(() => {
  if (isReadingAloud.value) stopReadAloud()
})
</script>

<template>
  <div
    :class="[
      'pointer-events-none absolute -bottom-6 flex w-max max-w-none flex-nowrap items-center gap-2 whitespace-nowrap text-xs leading-4 text-muted opacity-0 transition-opacity group-hover/message:pointer-events-auto group-hover/message:opacity-100 group-focus-within/message:pointer-events-auto group-focus-within/message:opacity-100',
      openTooltipKey || isReadAloudActive ? 'pointer-events-auto opacity-100' : '',
      message.role === 'user' ? 'right-0 justify-end' : 'left-0 justify-start'
    ]"
  >
    <UTooltip
      v-if="message.role === 'assistant' && tokenCount"
      :content="tooltipContent"
      :ui="richTooltipUi"
      @update:open="setTooltipOpen('tokens', $event)"
    >
      <span class="cursor-default whitespace-nowrap">
        {{ tokenCount }}
      </span>
      <template #content>
        <div class="min-w-44 space-y-1 text-xs">
          <div
            v-for="row in messageTokenDetails(message)"
            :key="row.label"
            class="flex items-center justify-between gap-4"
          >
            <span class="text-muted">{{ row.label }}</span>
            <span class="font-medium text-highlighted">{{ row.value }}</span>
          </div>
          <p class="max-w-56 pt-1 text-[11px] leading-4 text-muted">
            {{ messageTokenTooltipNote(message) }}
          </p>
        </div>
      </template>
    </UTooltip>
    <span v-if="message.role === 'assistant' && tokenCount" aria-hidden="true">·</span>
    <UTooltip
      v-if="message.role === 'assistant' && generationDuration"
      :content="tooltipContent"
      :ui="richTooltipUi"
      @update:open="setTooltipOpen('duration', $event)"
    >
      <span class="cursor-default whitespace-nowrap">
        {{ generationDuration }}
      </span>
      <template #content>
        <div class="min-w-44 space-y-1 text-xs">
          <div
            v-for="row in messageDurationDetails(message)"
            :key="row.label"
            class="flex items-center justify-between gap-4"
          >
            <span class="text-muted">{{ row.label }}</span>
            <span class="font-medium text-highlighted">{{ row.value }}</span>
          </div>
          <p class="max-w-56 pt-1 text-[11px] leading-4 text-muted">
            Total is wall-clock from run start to completion; tool and waiting time are measured when events are available.
          </p>
        </div>
      </template>
    </UTooltip>
    <span v-if="message.role === 'assistant' && generationDuration" aria-hidden="true">·</span>
    <span class="cursor-default whitespace-nowrap" :title="messageTimestampTitle(message.createdAt)">
      {{ formatMessageTimestamp(message.createdAt) }}
    </span>
    <UTooltip
      v-if="message.role === 'user'"
      text="Edit prompt"
      :content="tooltipContent"
      @update:open="setTooltipOpen('edit', $event)"
    >
      <button
        type="button"
        class="inline-flex size-4 flex-none items-center justify-center text-muted hover:text-highlighted focus-visible:outline-2 focus-visible:outline-primary/50"
        aria-label="Edit message"
        :disabled="savingEditedMessageId === message.id || message.localStatus === 'failed'"
        @click="emit('edit', message)"
      >
        <UIcon name="i-lucide-pencil" class="size-3" />
      </button>
    </UTooltip>
    <UTooltip
      v-else
      text="Regenerate response"
      :content="tooltipContent"
      @update:open="setTooltipOpen('regenerate', $event)"
    >
      <button
        type="button"
        class="inline-flex size-4 flex-none items-center justify-center text-muted hover:text-highlighted focus-visible:outline-2 focus-visible:outline-primary/50 disabled:pointer-events-none disabled:opacity-50"
        aria-label="Regenerate response"
        :disabled="isRunning"
        @click="emit('regenerate', message)"
      >
        <UIcon name="i-lucide-rotate-ccw" class="size-3" />
      </button>
    </UTooltip>
    <UTooltip
      text="Copy"
      :content="tooltipContent"
      @update:open="setTooltipOpen('copy', $event)"
    >
      <button
        type="button"
        class="inline-flex size-4 flex-none items-center justify-center text-muted hover:text-highlighted focus-visible:outline-2 focus-visible:outline-primary/50"
        :aria-label="copiedMessageId === message.id ? 'Copied message' : 'Copy message'"
        @click="emit('copy', message)"
      >
        <UIcon :name="copiedMessageId === message.id ? 'i-lucide-check' : 'i-lucide-copy'" class="size-3" />
      </button>
    </UTooltip>
    <button
      v-if="message.role === 'assistant'"
      type="button"
      class="inline-flex size-4 flex-none items-center justify-center text-muted hover:text-highlighted focus-visible:outline-2 focus-visible:outline-primary/50"
      :class="isReadingAloud || isGeneratingAloud ? 'text-primary hover:text-primary' : ''"
      :aria-label="readAloudAriaLabel"
      @click="readAloud(message)"
    >
      <UIcon
        :name="isReadingAloud ? 'i-lucide-square' : (isGeneratingAloud ? 'i-lucide-loader-circle' : 'i-lucide-volume-2')"
        class="size-3"
        :class="isGeneratingAloud ? 'animate-spin' : ''"
      />
    </button>
    <span v-if="message.role === 'assistant' && readAloudStatusDetail" aria-hidden="true">·</span>
    <em
      v-if="message.role === 'assistant' && readAloudStatusDetail"
      class="cursor-default whitespace-nowrap text-muted"
    >
      {{ readAloudStatusDetail }}
    </em>
  </div>
</template>
