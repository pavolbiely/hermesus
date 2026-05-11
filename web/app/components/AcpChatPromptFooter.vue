<script setup lang="ts">
import type { ChatPromptAttachment } from '~/types/chat'

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

type SelectItem = { label: string, value: string }

type Props = {
  submitStatus: 'ready' | 'submitted' | 'streaming' | 'error'
  submitDisabled?: boolean
  workspaces?: SelectItem[]
  selectedWorkspace?: string | null
  workspacesLoading?: boolean
  workspaceLabel?: string
  attachments?: ChatPromptAttachment[]
  attachmentsLoading?: boolean
  models?: SelectItem[]
  selectedModel?: string | null
  modelLabel?: string
  modes?: SelectItem[]
  selectedMode?: string | null
  reasoningLabel?: string
  updatingSessionConfig?: boolean
  showWorkspace?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  submitDisabled: false,
  workspaces: () => [],
  selectedWorkspace: null,
  workspacesLoading: false,
  workspaceLabel: 'Workspace',
  attachments: () => [],
  attachmentsLoading: false,
  models: () => [],
  selectedModel: null,
  modelLabel: 'Model',
  modes: () => [],
  selectedMode: null,
  reasoningLabel: 'Reasoning',
  updatingSessionConfig: false,
  showWorkspace: true
})

const emit = defineEmits<{
  stop: []
  updateSelectedWorkspace: [path: string | null]
  attachFiles: [files: File[]]
  removeAttachment: [id: string]
  voiceText: [text: string]
  voiceError: [message: string]
  updateSelectedModel: [model: string]
  updateSelectedMode: [mode: string]
}>()

const fileInput = ref<HTMLInputElement | null>(null)
const voiceStatus = ref<'idle' | 'listening' | 'error'>('idle')
const recognition = ref<SpeechRecognitionInstance | null>(null)

const controlsDisabled = computed(() => props.submitStatus === 'submitted' || props.submitStatus === 'streaming')
const selectedModelUnavailable = computed(() => Boolean(props.selectedModel && props.models.length && !props.models.some(item => item.value === props.selectedModel)))
const selectedModeUnavailable = computed(() => Boolean(props.selectedMode && props.modes.length && !props.modes.some(item => item.value === props.selectedMode)))
const modelButtonLabel = computed(() => props.models.find(item => item.value === props.selectedModel)?.label || props.modelLabel || 'Model')
const reasoningButtonLabel = computed(() => props.modes.find(item => item.value === props.selectedMode)?.label || props.reasoningLabel || 'Reasoning')
const voiceIsListening = computed(() => voiceStatus.value === 'listening')
const voiceTooltip = computed(() => voiceIsListening.value ? 'Stop voice input' : 'Dictate by voice')
const submitAriaLabel = computed(() => props.submitStatus === 'submitted' || props.submitStatus === 'streaming' ? 'Stop prompt' : 'Send prompt')
const promptFooterButtonClass = 'justify-center hover:!bg-transparent active:!bg-transparent focus-visible:!bg-transparent'
const promptFooterIconButtonClass = `${promptFooterButtonClass} size-7 p-0`
const promptFooterButtonUi = { leadingIcon: 'shrink-0', trailingIcon: 'shrink-0' }

const permissionItems = [
  { label: 'Plan', icon: 'i-lucide-pencil-ruler' },
  { label: 'Chat', icon: 'i-lucide-message-circle' },
  { label: 'Agent', icon: 'i-lucide-hand', type: 'checkbox' as const, checked: true },
  { label: 'Full Access', icon: 'i-lucide-shield-check' }
]

const workspaceItems = computed(() => [
  {
    label: 'No workspace',
    icon: 'i-lucide-folder-minus',
    type: 'checkbox' as const,
    checked: props.selectedWorkspace === null,
    onSelect: () => emit('updateSelectedWorkspace', null)
  },
  ...props.workspaces.map(workspace => ({
    label: workspace.label,
    icon: 'i-lucide-folder',
    type: 'checkbox' as const,
    checked: workspace.value === props.selectedWorkspace,
    onSelect: () => emit('updateSelectedWorkspace', workspace.value)
  }))
])

const modelItems = computed(() => {
  if (!props.models.length) return [{ label: 'No ACP models', disabled: true }]
  return props.models.map(model => ({
    label: model.label,
    type: 'checkbox' as const,
    checked: model.value === props.selectedModel,
    onSelect: () => emit('updateSelectedModel', model.value)
  }))
})

const modeItems = computed(() => {
  if (!props.modes.length) return [{ label: 'No reasoning modes', disabled: true }]
  return props.modes.map(mode => ({
    label: mode.label,
    type: 'checkbox' as const,
    checked: mode.value === props.selectedMode,
    onSelect: () => emit('updateSelectedMode', mode.value)
  }))
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

function formatFileSize(bytes: number) {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}

function attachmentPreviewUrl(attachment: ChatPromptAttachment) {
  if (!attachment.type.startsWith('image/') || !attachment.data) return null
  return `data:${attachment.type};base64,${attachment.data}`
}

function toggleVoice() {
  if (voiceIsListening.value) {
    stopVoice()
    return
  }
  startBrowserVoiceInput()
}

function stopVoice() {
  const instance = recognition.value
  if (!instance) {
    voiceStatus.value = 'idle'
    return
  }

  instance.onresult = null
  instance.onerror = null
  instance.onend = null
  instance.stop()
  recognition.value = null
  voiceStatus.value = 'idle'
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
  <div class="flex w-full min-w-0 flex-col gap-2">
    <div v-if="attachments.length" class="flex min-w-0 flex-wrap gap-1.5">
      <UBadge
        v-for="attachment in attachments"
        :key="attachment.id"
        color="neutral"
        variant="soft"
        size="sm"
        class="group relative max-w-56 gap-1 rounded-lg pr-1"
      >
        <UIcon :name="attachment.type.startsWith('image/') ? 'i-lucide-image' : 'i-lucide-paperclip'" class="size-3 shrink-0" />
        <span class="min-w-0 truncate">{{ attachment.name }}</span>
        <span class="shrink-0 text-muted">{{ formatFileSize(attachment.size) }}</span>
        <div
          v-if="attachmentPreviewUrl(attachment)"
          class="pointer-events-none absolute bottom-full left-0 z-50 mb-2 hidden rounded-xl border border-default bg-default p-1 shadow-lg group-hover:block group-focus-within:block"
        >
          <img
            :src="attachmentPreviewUrl(attachment) || undefined"
            :alt="attachment.name"
            class="max-h-56 max-w-72 rounded-lg object-contain"
          >
        </div>
        <UButton
          aria-label="Remove attachment"
          icon="i-lucide-x"
          color="neutral"
          variant="ghost"
          size="xs"
          class="size-4 p-0"
          :disabled="controlsDisabled"
          @click="emit('removeAttachment', attachment.id)"
        />
      </UBadge>
    </div>

    <div class="flex min-w-0 items-center justify-between gap-2">
      <div class="flex min-w-0 items-center gap-1.5 overflow-x-auto">
        <input ref="fileInput" type="file" multiple class="hidden" @change="onFileChange">
        <UTooltip text="Attach file">
          <UButton
            aria-label="Attach file"
            icon="i-lucide-paperclip"
            color="neutral"
            variant="ghost"
            size="sm"
            :class="promptFooterIconButtonClass"
            :ui="promptFooterButtonUi"
            :disabled="controlsDisabled"
            :loading="attachmentsLoading"
            @click="openFilePicker"
          />
        </UTooltip>

        <UDropdownMenu size="sm" :items="permissionItems" :content="{ align: 'start', side: 'top', sideOffset: 8 }">
          <UButton
            aria-label="Permission mode"
            icon="i-lucide-hand"
            trailing-icon="i-lucide-chevron-down"
            color="neutral"
            variant="ghost"
            size="sm"
            :class="['shrink-0', promptFooterButtonClass]"
            :ui="promptFooterButtonUi"
          >
            Agent
          </UButton>
        </UDropdownMenu>

        <UDropdownMenu
          v-if="showWorkspace"
          size="sm"
          :items="workspaceItems"
          :disabled="workspacesLoading"
          :content="{ align: 'start', side: 'top', sideOffset: 8 }"
        >
          <UButton
            aria-label="Workspace"
            icon="i-lucide-folder"
            trailing-icon="i-lucide-chevron-down"
            color="neutral"
            variant="ghost"
            size="sm"
            :class="['max-w-48 shrink-0', promptFooterButtonClass]"
            :ui="promptFooterButtonUi"
            :loading="workspacesLoading"
          >
            <span class="min-w-0 truncate">{{ workspaceLabel }}</span>
          </UButton>
        </UDropdownMenu>
      </div>

      <div class="flex shrink-0 items-center gap-1.5">
        <UDropdownMenu
          size="sm"
          :items="modelItems"
          :filter="{ placeholder: 'Search models...' }"
          :content="{ align: 'end', side: 'top', sideOffset: 8 }"
        >
          <UButton
            aria-label="Model"
            icon="i-lucide-cpu"
            trailing-icon="i-lucide-chevron-down"
            :color="selectedModelUnavailable ? 'error' : 'neutral'"
            :variant="selectedModelUnavailable ? 'soft' : 'ghost'"
            size="sm"
            :class="['max-w-44 shrink-0', promptFooterButtonClass]"
            :ui="promptFooterButtonUi"
            :disabled="updatingSessionConfig || !models.length"
          >
            <span class="min-w-0 truncate">{{ modelButtonLabel }}</span>
          </UButton>
        </UDropdownMenu>

        <UDropdownMenu size="sm" :items="modeItems" :content="{ align: 'end', side: 'top', sideOffset: 8 }">
          <UButton
            aria-label="Reasoning effort"
            icon="i-lucide-brain"
            trailing-icon="i-lucide-chevron-down"
            :color="selectedModeUnavailable ? 'error' : 'neutral'"
            :variant="selectedModeUnavailable ? 'soft' : 'ghost'"
            size="sm"
            :class="['max-w-36 shrink-0', promptFooterButtonClass]"
            :ui="promptFooterButtonUi"
            :disabled="updatingSessionConfig || !modes.length"
          >
            <span class="min-w-0 truncate">{{ reasoningButtonLabel }}</span>
          </UButton>
        </UDropdownMenu>

        <UTooltip :text="voiceTooltip">
          <UButton
            :aria-label="voiceTooltip"
            icon="i-lucide-mic"
            :color="voiceIsListening ? 'error' : 'neutral'"
            :variant="voiceIsListening ? 'soft' : 'ghost'"
            size="sm"
            :disabled="controlsDisabled"
            :class="[promptFooterIconButtonClass, voiceIsListening ? 'animate-pulse hover:!bg-error/10 active:!bg-error/10 focus-visible:!bg-error/10' : undefined]"
            :ui="promptFooterButtonUi"
            @click="toggleVoice"
          />
        </UTooltip>

        <UChatPromptSubmit
          :status="submitStatus"
          :disabled="submitDisabled"
          :aria-label="submitAriaLabel"
          submitted-icon="i-lucide-square"
          submitted-color="error"
          submitted-variant="solid"
          streaming-icon="i-lucide-square"
          streaming-color="error"
          streaming-variant="solid"
          @stop="emit('stop')"
        />
      </div>
    </div>
  </div>
</template>
