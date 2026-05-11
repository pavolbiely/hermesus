<script setup lang="ts">
import type { ChatPromptAttachment, SlashCommand } from '~/types/chat'
import type { QueuedMessage } from '~/utils/queuedMessages'
import { filesFromClipboard } from '~/utils/clipboard'

type SelectItem = { label: string, value: string }
type SubmitStatus = 'ready' | 'submitted' | 'streaming' | 'error'

const input = defineModel<string>({ required: true })

const props = withDefaults(defineProps<{
  commands?: SlashCommand[]
  queuedMessages?: QueuedMessage[]
  steeringId?: string | null
  loading?: boolean
  submitStatus: SubmitStatus
  submitDisabled?: boolean
  attachments?: ChatPromptAttachment[]
  attachmentsLoading?: boolean
  workspaces?: SelectItem[]
  selectedWorkspace?: string | null
  workspacesLoading?: boolean
  workspaceLabel?: string
  models?: SelectItem[]
  selectedModel?: string | null
  modelLabel?: string
  modes?: SelectItem[]
  selectedMode?: string | null
  reasoningLabel?: string
  updatingSessionConfig?: boolean
}>(), {
  commands: () => [],
  queuedMessages: () => [],
  steeringId: null,
  loading: false,
  submitDisabled: false,
  attachments: () => [],
  attachmentsLoading: false,
  workspaces: () => [],
  selectedWorkspace: null,
  workspacesLoading: false,
  workspaceLabel: 'Workspace',
  models: () => [],
  selectedModel: null,
  modelLabel: 'Model',
  modes: () => [],
  selectedMode: null,
  reasoningLabel: 'Reasoning',
  updatingSessionConfig: false
})

const emit = defineEmits<{
  submit: []
  editQueued: [id: string]
  deleteQueued: [id: string]
  steerQueued: [id: string]
  stop: []
  attachFiles: [files: File[]]
  removeAttachment: [id: string]
  voiceText: [text: string]
  voiceError: [message: string]
  updateSelectedWorkspace: [path: string | null]
  updateSelectedModel: [model: string]
  updateSelectedMode: [mode: string]
}>()

const promptContainer = ref<HTMLElement | null>(null)
const canAttachPastedFiles = computed(() => !props.loading && !props.attachmentsLoading && props.submitStatus !== 'submitted' && props.submitStatus !== 'streaming')
const slashCommands = useStaticSlashCommands({ input, commands: computed(() => props.commands) })
const {
  selectSlashCommand,
  onPromptArrowDown,
  onPromptArrowUp,
  onPromptEscape,
  onPromptEnter: onPromptAutocompleteEnter
} = useChatSlashCommandAutocomplete({
  input,
  slashCommands
})

function focus() {
  promptContainer.value?.querySelector('textarea')?.focus()
}

function onPaste(event: ClipboardEvent) {
  const files = filesFromClipboard(event)
  if (!files.length) return

  event.preventDefault()
  if (canAttachPastedFiles.value) emit('attachFiles', files)
}

onMounted(() => {
  promptContainer.value?.addEventListener('paste', onPaste)
})

onBeforeUnmount(() => {
  promptContainer.value?.removeEventListener('paste', onPaste)
})

defineExpose({ focus })
</script>

<template>
  <div ref="promptContainer" class="relative">
    <ChatSlashCommandMenu
      :commands="slashCommands.filteredCommands.value"
      :open="slashCommands.isOpen.value"
      :loading="slashCommands.loading.value"
      :highlighted-index="slashCommands.highlightedIndex.value"
      @select="selectSlashCommand"
      @highlight="slashCommands.highlightedIndex.value = $event"
    />
    <div
      v-if="queuedMessages.length"
      class="absolute inset-x-0 bottom-full z-10 pb-2"
    >
      <ChatQueuedMessages
        :messages="queuedMessages"
        :steering-id="steeringId"
        :disabled="loading"
        @edit="emit('editQueued', $event)"
        @delete="emit('deleteQueued', $event)"
        @steer="emit('steerQueued', $event)"
      />
    </div>
    <UChatPrompt
      v-model="input"
      :maxrows="6"
      :should-auto-scroll="true"
      :should-scroll-to-bottom="true"
      :auto-scroll="true"
      placeholder="Message Hermes through ACP…"
      @submit="emit('submit')"
      @keydown.down="onPromptArrowDown"
      @keydown.up="onPromptArrowUp"
      @keydown.esc="onPromptEscape"
      @keydown.enter="onPromptAutocompleteEnter"
    >
      <template #footer>
        <AcpChatPromptFooter
          :submit-status="submitStatus"
          :submit-disabled="submitDisabled"
          :attachments="attachments"
          :attachments-loading="attachmentsLoading"
          :workspaces="workspaces"
          :selected-workspace="selectedWorkspace"
          :workspaces-loading="workspacesLoading"
          :workspace-label="workspaceLabel"
          :models="models"
          :selected-model="selectedModel"
          :model-label="modelLabel"
          :modes="modes"
          :selected-mode="selectedMode"
          :reasoning-label="reasoningLabel"
          :updating-session-config="updatingSessionConfig"
          @stop="emit('stop')"
          @attach-files="emit('attachFiles', $event)"
          @remove-attachment="emit('removeAttachment', $event)"
          @voice-text="emit('voiceText', $event)"
          @voice-error="emit('voiceError', $event)"
          @update-selected-workspace="emit('updateSelectedWorkspace', $event)"
          @update-selected-model="emit('updateSelectedModel', $event)"
          @update-selected-mode="emit('updateSelectedMode', $event)"
        />
      </template>
    </UChatPrompt>
  </div>
</template>
