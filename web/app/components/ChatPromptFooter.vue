<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'
import type { WebChatAttachment, WebChatModelCapability, WebChatWorkspace } from '~/types/web-chat'

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

type ChatPromptFooterProps = {
  submitStatus: 'ready' | 'submitted' | 'streaming' | 'error'
  workspaces?: WebChatWorkspace[]
  selectedWorkspace?: string | null
  workspaceInvalidSignal?: number
  workspacesLoading?: boolean
  attachments?: WebChatAttachment[]
  attachmentsLoading?: boolean
  models?: WebChatModelCapability[]
  selectedModel?: string | null
  selectedReasoningEffort?: string | null
  capabilitiesLoading?: boolean
}

const props = withDefaults(defineProps<ChatPromptFooterProps>(), {
  workspaces: () => [],
  selectedWorkspace: null,
  workspaceInvalidSignal: 0,
  workspacesLoading: false,
  attachments: () => [],
  attachmentsLoading: false,
  models: () => [],
  selectedModel: null,
  selectedReasoningEffort: null,
  capabilitiesLoading: false
})

const emit = defineEmits<{
  stop: []
  updateSelectedWorkspace: [path: string | null]
  attachFiles: [files: File[]]
  removeAttachment: [id: string]
  voiceText: [text: string]
  voiceError: [message: string]
  updateSelectedModel: [model: string]
  updateSelectedReasoningEffort: [reasoningEffort: string]
}>()

const fileInput = ref<HTMLInputElement | null>(null)
const workspaceInvalid = ref(false)
const voiceStatus = ref<'idle' | 'listening' | 'error'>('idle')
const recognition = ref<SpeechRecognitionInstance | null>(null)

const selectedModelCapability = computed(() => props.models.find(model => model.id === props.selectedModel) || null)
const reasoningEfforts = computed(() => selectedModelCapability.value?.reasoningEfforts || [])
const selectedWorkspaceItem = computed(() => props.workspaces.find(workspace => workspace.path === props.selectedWorkspace) || null)
const controlsDisabled = computed(() => props.submitStatus === 'submitted' || props.submitStatus === 'streaming')

const workspaceLabel = computed(() => selectedWorkspaceItem.value?.label || 'No workspace')
const modelLabel = computed(() => selectedModelCapability.value?.label || props.selectedModel || 'Model')
const reasoningLabel = computed(() => props.selectedReasoningEffort || 'Reasoning')
const voiceIsListening = computed(() => voiceStatus.value === 'listening')
const voiceTooltip = computed(() => voiceIsListening.value ? 'Stop voice input' : 'Dictate by voice')
const voiceAriaLabel = computed(() => voiceIsListening.value ? 'Stop voice input' : 'Dictate by voice')

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

const workspaceItems = computed<DropdownMenuItem[]>(() => [
  {
    label: 'No workspace',
    icon: 'i-lucide-folder',
    checked: !props.selectedWorkspace,
    onSelect: () => emit('updateSelectedWorkspace', null),
    trailingIcon: !props.selectedWorkspace ? 'i-lucide-check' : undefined
  },
  ...props.workspaces.map(workspace => ({
    label: workspace.label,
    icon: 'i-lucide-folder',
    checked: workspace.path === props.selectedWorkspace,
    onSelect: () => emit('updateSelectedWorkspace', workspace.path),
    trailingIcon: workspace.path === props.selectedWorkspace ? 'i-lucide-check' : undefined
  }))
])

const modelItems = computed<DropdownMenuItem[]>(() => props.models.map(model => ({
  label: model.label,
  checked: model.id === props.selectedModel,
  onSelect: () => emit('updateSelectedModel', model.id),
  trailingIcon: model.id === props.selectedModel ? 'i-lucide-check' : undefined
})))

const reasoningItems = computed<DropdownMenuItem[]>(() => reasoningEfforts.value.map(reasoningEffort => ({
  label: reasoningEffort,
  checked: reasoningEffort === props.selectedReasoningEffort,
  onSelect: () => emit('updateSelectedReasoningEffort', reasoningEffort),
  trailingIcon: reasoningEffort === props.selectedReasoningEffort ? 'i-lucide-check' : undefined
})))

function openFilePicker() {
  if (!controlsDisabled.value && !props.attachmentsLoading) fileInput.value?.click()
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (files.length) emit('attachFiles', files)
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

function toggleVoice() {
  if (voiceStatus.value === 'listening') {
    stopVoice()
    return
  }

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
  <div class="flex min-w-0 flex-1 flex-col gap-1.5 overflow-hidden">
    <div v-if="attachments.length" class="flex min-w-0 flex-wrap gap-1.5 px-1">
      <UBadge
        v-for="attachment in attachments"
        :key="attachment.id"
        color="neutral"
        variant="soft"
        class="max-w-48 gap-1"
        :title="attachment.path"
      >
        <UIcon :name="attachment.mediaType.startsWith('image/') ? 'i-lucide-image' : 'i-lucide-file'" class="size-3.5 shrink-0" />
        <span class="truncate">{{ attachment.name }}</span>
        <UButton
          icon="i-lucide-x"
          color="neutral"
          variant="ghost"
          size="xs"
          :disabled="controlsDisabled"
          @click="emit('removeAttachment', attachment.id)"
        />
      </UBadge>
    </div>

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
          :color="voiceIsListening ? 'error' : 'neutral'"
          :variant="voiceIsListening ? 'soft' : 'ghost'"
          size="sm"
          :disabled="controlsDisabled"
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

        <UDropdownMenu :items="modelItems" :disabled="capabilitiesLoading || !modelItems.length" size="sm" :content="{ align: 'start', side: 'top', sideOffset: 8 }">
          <UButton aria-label="Model" icon="i-lucide-cpu" trailing-icon="i-lucide-chevron-down" color="neutral" variant="ghost" size="sm" class="shrink-0" :loading="capabilitiesLoading && !modelItems.length">
            {{ modelLabel }}
          </UButton>
        </UDropdownMenu>

        <UDropdownMenu :items="reasoningItems" :disabled="capabilitiesLoading || !reasoningItems.length" size="sm" :content="{ align: 'start', side: 'top', sideOffset: 8 }">
          <UButton aria-label="Reasoning effort" icon="i-lucide-brain" trailing-icon="i-lucide-chevron-down" color="neutral" variant="ghost" size="sm" class="shrink-0" :disabled="capabilitiesLoading || !reasoningItems.length" :loading="capabilitiesLoading && !reasoningItems.length">
            {{ reasoningLabel }}
          </UButton>
        </UDropdownMenu>
      </div>
    </div>
  </div>

  <UChatPromptSubmit :status="submitStatus" @stop="emit('stop')" />
</template>

<style scoped>
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
