<script setup lang="ts">
import type { WebChatAttachment, WebChatCommand, WebChatModelCapability, WebChatWorkspace } from '~/types/web-chat'
import { readAloudElevenLabsApiKey, voiceInputOpenAIApiKey, voiceInputProvider } from '~/utils/readAloudPreferences'

type SpeechRecognitionConstructor = new () => SpeechRecognitionInstance
type SpeechRecognitionResultLike = { isFinal: boolean, 0: { transcript: string } }
type SpeechRecognitionEventLike = { resultIndex: number, results: ArrayLike<SpeechRecognitionResultLike> }
type SpeechRecognitionInstance = {
  continuous: boolean
  interimResults: boolean
  lang: string
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: { error?: string }) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort?: () => void
}

type SpeechWindow = Window & {
  SpeechRecognition?: SpeechRecognitionConstructor
  webkitSpeechRecognition?: SpeechRecognitionConstructor
}

type ChatContextUsage = {
  usedTokens: number
  maxTokens: number
  autoCompressTokens: number
  compressionCount?: number
  estimated?: boolean
}

type ChatPromptFooterProps = {
  submitStatus: 'ready' | 'submitted' | 'streaming' | 'error'
  submitDisabled?: boolean
  contextUsage?: ChatContextUsage | null
  workspaces?: WebChatWorkspace[]
  selectedWorkspace?: string | null
  workspaceInvalidSignal?: number
  workspacesLoading?: boolean
  attachments?: WebChatAttachment[]
  attachmentsLoading?: boolean
  models?: WebChatModelCapability[]
  selectedModel?: string | null
  selectedProvider?: string | null
  selectedReasoningEffort?: string | null
  capabilitiesLoading?: boolean
  capabilitiesRefreshing?: boolean
  capabilitiesError?: string | null
  slashCommands?: WebChatCommand[]
  slashCommandsOpen?: boolean
  slashCommandsLoading?: boolean
  highlightedSlashCommandIndex?: number
}

const props = withDefaults(defineProps<ChatPromptFooterProps>(), {
  submitDisabled: false,
  workspaces: () => [],
  selectedWorkspace: null,
  workspaceInvalidSignal: 0,
  workspacesLoading: false,
  attachments: () => [],
  attachmentsLoading: false,
  models: () => [],
  selectedModel: null,
  selectedProvider: null,
  selectedReasoningEffort: null,
  capabilitiesLoading: false,
  capabilitiesRefreshing: false,
  capabilitiesError: null,
  slashCommands: () => [],
  slashCommandsOpen: false,
  slashCommandsLoading: false,
  highlightedSlashCommandIndex: 0
})

const emit = defineEmits<{
  stop: []
  updateSelectedWorkspace: [path: string | null]
  attachFiles: [files: File[]]
  removeAttachment: [id: string]
  voiceText: [text: string]
  voiceError: [message: string]
  updateSelectedModel: [model: string]
  updateSelectedProvider: [provider: string | null]
  updateSelectedReasoningEffort: [reasoningEffort: string]
  refreshModels: []
  selectSlashCommand: [command: WebChatCommand]
  highlightSlashCommand: [index: number]
}>()

const fileInput = ref<HTMLInputElement | null>(null)
const workspaceInvalid = ref(false)
const voiceStatus = ref<'idle' | 'listening' | 'transcribing' | 'error'>('idle')
const recognition = ref<SpeechRecognitionInstance | null>(null)
const voiceRecorder = ref<MediaRecorder | null>(null)
const voiceStream = ref<MediaStream | null>(null)
const voiceChunks = ref<Blob[]>([])
const api = useHermesApi()
const controlsDisabled = computed(() => props.submitStatus === 'submitted' || props.submitStatus === 'streaming')
const contextUsagePercent = computed(() => {
  const usage = props.contextUsage
  if (!usage || usage.maxTokens <= 0) return null
  return Math.min(100, Math.max(0, Math.round((usage.usedTokens / usage.maxTokens) * 100)))
})
const contextUsageProgressStyle = computed(() => {
  if (contextUsagePercent.value === null) return undefined
  const percent = contextUsagePercent.value
  const hue = Math.round(142 - (142 * percent / 100))
  return {
    '--context-usage-progress': `${percent}%`,
    '--context-usage-color': `hsl(${hue} 76% 44%)`
  }
})
const contextUsageLeft = computed(() => {
  const usage = props.contextUsage
  return usage ? Math.max(0, usage.maxTokens - usage.usedTokens) : 0
})
const contextAutoCompressPercent = computed(() => {
  const usage = props.contextUsage
  if (!usage || usage.maxTokens <= 0) return null
  return Math.min(100, Math.max(0, Math.round((usage.autoCompressTokens / usage.maxTokens) * 100)))
})
const contextCompressionCount = computed(() => Math.max(0, props.contextUsage?.compressionCount || 0))

const {
  modelPickerOpen,
  modelSearch,
  selectedModelUnavailable,
  selectedWorkspaceItem,
  workspaceLabel,
  modelLabel,
  reasoningLabel,
  workspaceItems,
  filteredModelGroups,
  hasModelItems,
  selectModel,
  reasoningItems
} = useChatPromptSelectorState(props, emit)
const voiceIsListening = computed(() => voiceStatus.value === 'listening')
const voiceIsBusy = computed(() => voiceStatus.value === 'listening' || voiceStatus.value === 'transcribing')
const voiceTooltip = computed(() => {
  if (voiceStatus.value === 'transcribing') return 'Transcribing voice input'
  return voiceIsListening.value ? 'Stop voice input' : 'Dictate by voice'
})
const voiceAriaLabel = computed(() => voiceTooltip.value)

function formatContextTokens(value: number) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`
  return String(Math.round(value))
}

watch(() => props.workspaceInvalidSignal, (signal) => {
  if (!signal) return
  workspaceInvalid.value = false
  requestAnimationFrame(() => {
    workspaceInvalid.value = true
    window.setTimeout(() => {
      workspaceInvalid.value = false
    }, 650)
  })
})

function openFilePicker() {
  if (!controlsDisabled.value && !props.attachmentsLoading) fileInput.value?.click()
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (files.length) emit('attachFiles', files)
}

function stopVoiceStream() {
  voiceStream.value?.getTracks().forEach((track) => track.stop())
  voiceStream.value = null
}

function stopVoice() {
  const recorder = voiceRecorder.value
  if (recorder) {
    if (recorder.state !== 'inactive') recorder.stop()
    voiceRecorder.value = null
    return
  }

  const instance = recognition.value
  if (!instance) {
    voiceStatus.value = 'idle'
    stopVoiceStream()
    return
  }

  instance.onresult = null
  instance.onerror = null
  instance.onend = null
  instance.stop()
  recognition.value = null
  voiceStatus.value = 'idle'
}

async function toggleVoice() {
  if (voiceStatus.value === 'transcribing') return
  if (voiceStatus.value === 'listening') {
    stopVoice()
    return
  }

  const provider = voiceInputProvider()
  if (provider === 'elevenlabs' || provider === 'openai') {
    await startRemoteVoiceInput(provider)
    return
  }

  startBrowserVoiceInput()
}

function voiceInputApiKey(provider: 'elevenlabs' | 'openai') {
  return provider === 'elevenlabs' ? readAloudElevenLabsApiKey() : voiceInputOpenAIApiKey()
}

function voiceInputProviderLabel(provider: 'elevenlabs' | 'openai') {
  return provider === 'elevenlabs' ? 'ElevenLabs' : 'OpenAI'
}

function voiceInputErrorMessage(error: unknown, providerLabel: string) {
  const fallback = `Could not transcribe voice input with ${providerLabel}.`
  if (!error || typeof error !== 'object') return fallback
  const data = 'data' in error ? (error as { data?: unknown }).data : null
  if (data && typeof data === 'object' && 'detail' in data) {
    const detail = (data as { detail?: unknown }).detail
    if (typeof detail === 'string' && detail.trim()) return detail.trim()
  }
  if ('message' in error) {
    const message = (error as { message?: unknown }).message
    if (typeof message === 'string' && message.trim()) return message.trim()
  }
  return fallback
}

async function startRemoteVoiceInput(provider: 'elevenlabs' | 'openai') {
  const providerLabel = voiceInputProviderLabel(provider)
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
    voiceStatus.value = 'error'
    emit('voiceError', `${providerLabel} voice input needs browser microphone recording support.`)
    return
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const recorder = new MediaRecorder(stream)
    voiceStream.value = stream
    voiceRecorder.value = recorder
    voiceChunks.value = []
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) voiceChunks.value.push(event.data)
    }
    recorder.onerror = () => {
      voiceRecorder.value = null
      stopVoiceStream()
      voiceStatus.value = 'error'
      emit('voiceError', 'Could not capture voice input.')
    }
    recorder.onstop = async () => {
      const chunks = voiceChunks.value
      voiceRecorder.value = null
      voiceChunks.value = []
      stopVoiceStream()
      if (!chunks.length) {
        voiceStatus.value = 'idle'
        return
      }

      voiceStatus.value = 'transcribing'
      try {
        const audio = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
        const result = await api.transcribeSpeechInput(audio, {
          provider,
          apiKey: voiceInputApiKey(provider)
        })
        const text = result.text.trim()
        if (text) emit('voiceText', text)
        else emit('voiceError', `${providerLabel} returned an empty transcript.`)
        voiceStatus.value = 'idle'
      } catch (error) {
        voiceStatus.value = 'error'
        emit('voiceError', voiceInputErrorMessage(error, providerLabel))
      }
    }
    voiceStatus.value = 'listening'
    recorder.start()
  } catch {
    voiceRecorder.value = null
    stopVoiceStream()
    voiceStatus.value = 'error'
    emit('voiceError', 'Could not access the microphone.')
  }
}

function startBrowserVoiceInput() {
  const SpeechRecognition = (window as SpeechWindow).SpeechRecognition || (window as SpeechWindow).webkitSpeechRecognition
  if (!SpeechRecognition) {
    voiceStatus.value = 'error'
    emit('voiceError', 'Voice input is not supported in this browser.')
    return
  }

  const instance = new SpeechRecognition()
  recognition.value = instance
  instance.continuous = false
  instance.interimResults = false
  instance.lang = navigator.language || 'en-US'
  instance.onresult = (event) => {
    const transcript: string[] = []
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index]
      if (result?.isFinal && result[0]?.transcript) transcript.push(result[0].transcript)
    }
    const text = transcript.join(' ').trim()
    if (text) emit('voiceText', text)
  }
  instance.onerror = () => {
    recognition.value = null
    voiceStatus.value = 'error'
    emit('voiceError', 'Could not capture voice input.')
  }
  instance.onend = () => {
    recognition.value = null
    if (voiceStatus.value === 'listening') voiceStatus.value = 'idle'
  }
  voiceStatus.value = 'listening'
  instance.start()
}

onBeforeUnmount(() => {
  const recorder = voiceRecorder.value
  if (recorder && recorder.state !== 'inactive') recorder.stop()
  voiceRecorder.value = null
  voiceChunks.value = []
  stopVoiceStream()

  const instance = recognition.value
  if (!instance) return

  instance.onresult = null
  instance.onerror = null
  instance.onend = null
  instance.abort?.()
  recognition.value = null
})
</script>

<template>
  <div class="relative flex min-w-0 flex-1 flex-col gap-1.5 overflow-visible">
    <ChatSlashCommandMenu
      :open="slashCommandsOpen"
      :loading="slashCommandsLoading"
      :commands="slashCommands"
      :highlighted-index="highlightedSlashCommandIndex"
      @select="emit('selectSlashCommand', $event)"
      @highlight="emit('highlightSlashCommand', $event)"
    />

    <ChatAttachmentList
      :attachments="attachments"
      :disabled="controlsDisabled"
      @remove="emit('removeAttachment', $event)"
    />

    <div class="flex min-w-0 items-center gap-1.5 overflow-hidden">
      <input ref="fileInput" type="file" multiple class="hidden" @change="onFileChange">
      <UTooltip text="Attach file">
        <UButton
          aria-label="Attach file"
          icon="i-lucide-paperclip"
          color="neutral"
          variant="ghost"
          size="sm"
          :disabled="controlsDisabled"
          :loading="attachmentsLoading"
          @click="openFilePicker"
        />
      </UTooltip>

      <UTooltip :text="voiceTooltip">
        <UButton
          :aria-label="voiceAriaLabel"
          icon="i-lucide-mic"
          :color="voiceIsBusy ? 'error' : 'neutral'"
          :variant="voiceIsBusy ? 'soft' : 'ghost'"
          size="sm"
          :disabled="controlsDisabled || voiceStatus === 'transcribing'"
          :loading="voiceStatus === 'transcribing'"
          :class="voiceIsListening ? 'animate-pulse' : undefined"
          @click="toggleVoice"
        />
      </UTooltip>

      <USeparator orientation="vertical" class="mx-1 h-5" />

      <div class="flex min-w-0 items-center gap-1.5 overflow-x-auto">
        <UDropdownMenu :items="workspaceItems" :disabled="workspacesLoading" size="sm" :content="{ align: 'start', side: 'top', sideOffset: 8 }">
          <UButton
            aria-label="Workspace"
            icon="i-lucide-folder"
            trailing-icon="i-lucide-chevron-down"
            :color="workspaceInvalid ? 'error' : 'neutral'"
            :variant="workspaceInvalid ? 'soft' : 'ghost'"
            size="sm"
            class="shrink-0 transition-colors"
            :class="workspaceInvalid ? 'workspace-invalid-shake' : undefined"
            :title="selectedWorkspaceItem?.path"
            :loading="workspacesLoading"
          >
            {{ workspaceLabel }}
          </UButton>
        </UDropdownMenu>

        <UPopover
          v-model:open="modelPickerOpen"
          :content="{ align: 'start', side: 'top', sideOffset: 8 }"
          :ui="{ content: 'w-80 p-0' }"
        >
          <UButton
            aria-label="Model"
            icon="i-lucide-cpu"
            trailing-icon="i-lucide-chevron-down"
            :color="selectedModelUnavailable ? 'error' : 'neutral'"
            :variant="selectedModelUnavailable ? 'soft' : 'ghost'"
            size="sm"
            class="max-w-56 shrink-0"
            :title="selectedModelUnavailable ? 'Selected model is unavailable' : undefined"
          >
            <span class="min-w-0 truncate">{{ modelLabel }}</span>
            <UIcon v-if="capabilitiesLoading || capabilitiesRefreshing" name="i-lucide-cpu" class="ml-1 size-3 shrink-0 animate-spin text-muted" />
          </UButton>

          <template #content>
            <div class="w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-md bg-default text-sm">
              <div class="flex items-center gap-2 border-b border-default p-2">
                <UInput
                  v-model="modelSearch"
                  autofocus
                  icon="i-lucide-search"
                  placeholder="Search models..."
                  size="sm"
                  variant="none"
                  class="min-w-0 flex-1"
                />
                <UTooltip text="Refresh models">
                  <UButton
                    aria-label="Refresh models"
                    icon="i-lucide-refresh-cw"
                    loading-icon="i-lucide-cpu"
                    color="neutral"
                    variant="ghost"
                    size="xs"
                    :loading="capabilitiesRefreshing"
                    @click.stop="emit('refreshModels')"
                  />
                </UTooltip>
              </div>

              <div v-if="capabilitiesError" class="border-b border-default px-3 py-2 text-xs text-error">
                {{ capabilitiesError }}
              </div>

              <div v-if="!filteredModelGroups.length" class="px-3 py-6 text-center text-xs text-muted">
                No matching models
              </div>

              <div v-else class="max-h-72 overflow-y-auto p-1">
                <div v-for="group in filteredModelGroups" :key="group.providerLabel" class="py-1 first:pt-0">
                  <div class="px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted">
                    {{ group.providerLabel }}
                  </div>
                  <button
                    v-for="item in group.items"
                    :key="`${item.provider || 'auto'}:${item.model.id}`"
                    type="button"
                    class="flex w-full items-center justify-between gap-3 rounded-md px-2 py-1.5 text-left text-xs text-default hover:bg-elevated/60 hover:text-highlighted"
                    @click="selectModel(item)"
                  >
                    <span class="min-w-0">
                      <span class="block truncate">{{ item.label }}</span>
                    </span>
                    <UIcon
                      v-if="item.model.id === selectedModel && item.provider === selectedProvider"
                      name="i-lucide-check"
                      class="size-4 shrink-0 text-muted"
                    />
                  </button>
                </div>
              </div>
            </div>
          </template>
        </UPopover>

        <UDropdownMenu
          :items="reasoningItems"
          :disabled="!reasoningItems.length"
          size="sm"
          :content="{ align: 'start', side: 'top', sideOffset: 8 }"
        >
          <UButton
            aria-label="Reasoning effort"
            icon="i-lucide-cpu"
            loading-icon="i-lucide-cpu"
            trailing-icon="i-lucide-chevron-down"
            :color="selectedModelUnavailable ? 'error' : 'neutral'"
            :variant="selectedModelUnavailable ? 'soft' : 'ghost'"
            size="sm"
            class="shrink-0"
            :title="selectedModelUnavailable ? 'Selected model is unavailable' : undefined"
            :disabled="!reasoningItems.length"
            :loading="capabilitiesLoading && !reasoningItems.length && !selectedModel"
          >
            {{ reasoningLabel }}
          </UButton>
        </UDropdownMenu>
      </div>
    </div>
  </div>

  <div class="flex shrink-0 items-center gap-1.5">
    <UTooltip
      v-if="contextUsage && contextUsagePercent !== null"
      :content="{ side: 'top', sideOffset: 8, align: 'end' }"
      :ui="{ content: 'h-auto max-w-none items-stretch rounded-md bg-elevated px-3 py-2 text-default shadow-lg ring ring-default' }"
    >
      <UButton
        type="button"
        aria-label="Context window usage"
        color="neutral"
        variant="ghost"
        size="xs"
        class="context-usage-ring size-8 cursor-default justify-center rounded-full p-[2px] text-[10px] leading-none tabular-nums"
        :style="contextUsageProgressStyle"
        tabindex="-1"
      >
        <span class="flex size-full items-center justify-center rounded-full bg-default text-muted">
          {{ contextUsagePercent }}
        </span>
      </UButton>
      <template #content>
        <div class="min-w-52 space-y-1 text-xs">
          <p class="font-medium text-highlighted">Context window</p>
          <p>{{ contextUsagePercent }}% used ({{ formatContextTokens(contextUsageLeft) }} left)</p>
          <p>{{ formatContextTokens(contextUsage.usedTokens) }} / {{ formatContextTokens(contextUsage.maxTokens) }} tokens used{{ contextUsage.estimated ? ' (estimate)' : '' }}</p>
          <p v-if="contextCompressionCount > 0">Compressed {{ contextCompressionCount }}× (context generation {{ contextCompressionCount + 1 }})</p>
          <p v-else>No compression yet</p>
          <p class="text-muted">Auto-compress at {{ formatContextTokens(contextUsage.autoCompressTokens) }}{{ contextAutoCompressPercent === null ? '' : ` (${contextAutoCompressPercent}%)` }}</p>
        </div>
      </template>
    </UTooltip>

    <UChatPromptSubmit
      :status="submitStatus"
      :disabled="submitDisabled"
      submitted-color="error"
      submitted-variant="solid"
      streaming-color="error"
      streaming-variant="solid"
      @stop="emit('stop')"
    />
  </div>
</template>

<style scoped>
.context-usage-ring {
  background: conic-gradient(var(--context-usage-color, var(--ui-primary)) var(--context-usage-progress), var(--ui-border) 0);
}

.workspace-invalid-shake {
  animation: workspace-invalid-shake 480ms ease-in-out;
}

@keyframes workspace-invalid-shake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-4px); }
  40% { transform: translateX(4px); }
  60% { transform: translateX(-3px); }
  80% { transform: translateX(3px); }
}
</style>
