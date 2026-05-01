<script setup lang="ts">
import { playNotificationSound, prepareNotificationSound } from '../utils/notificationSound'
import { filesFromClipboard } from '~/utils/clipboard'
import { NEW_CHAT_DRAFT_ID } from '~/utils/chatDrafts'

const { input, clearDraft } = useChatDraft(NEW_CHAT_DRAFT_ID)
const loading = ref(false)
const error = ref<Error | undefined>()
const workspaceInvalidSignal = ref(0)
const api = useHermesApi()
const router = useRouter()
const refreshSessions = inject<() => Promise<void> | void>('refreshSessions')
const composer = useChatComposerCapabilities()
const providerUsage = useProviderUsage(
  composer.selectedProvider,
  composer.selectedModel
)
const activeChatRuns = useActiveChatRuns()
const context = useChatComposerContext()
const newChatRequest = useNewChatRequest()
const toast = useToast()
const slashCommands = useSlashCommands({ input })

onMounted(() => {
  void initializeComposer()
})

async function initializeComposer() {
  try {
    await Promise.all([composer.initializeForNewChat(), context.initialize()])
  } catch (err) {
    showError(err, 'Could not initialize new chat')
  }
}

watch(
  () => newChatRequest.request.value,
  (request) => {
    if (!request.id || request.consumed) return

    context.selectWorkspace(request.workspace)
    context.clearAttachments()
    clearDraft()
    error.value = undefined
    newChatRequest.markConsumed(request.id)
  },
  { immediate: true }
)

function appendVoiceText(text: string) {
  input.value = input.value ? `${input.value} ${text}` : text
}

function showError(err: unknown, fallback: string) {
  const message = getHermesErrorMessage(err, fallback)
  error.value = new Error(message)
  toast.add({ color: 'error', title: fallback, description: message })
}

async function attachFiles(files: File[]) {
  try {
    await context.uploadFiles(files)
  } catch (err) {
    showError(err, 'Could not upload attachment.')
  }
}

const {
  isDraggingFiles,
  onPromptDragEnter,
  onPromptDragOver,
  onPromptDragLeave,
  onPromptDrop
} = useChatAttachmentDrop({
  disabled: computed(() => loading.value || context.attachmentsLoading.value),
  attachFiles,
  toast,
  unavailableTitle: 'Attachment upload is already in progress'
})

async function onPromptPaste(event: ClipboardEvent) {
  const files = filesFromClipboard(event)
  if (!files.length) return

  event.preventDefault()
  if (loading.value || context.attachmentsLoading.value) {
    toast.add({ color: 'warning', title: 'Attachment upload is already in progress' })
    return
  }

  await attachFiles(files)
}

function showVoiceError(message: string) {
  showError(new Error(message), 'Voice input failed')
}

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

async function onSubmit() {
  const message = input.value.trim()
  if (!message || loading.value) return
  if (!context.selectedWorkspace.value) {
    workspaceInvalidSignal.value += 1
    return
  }

  loading.value = true
  error.value = undefined
  void prepareNotificationSound()
  try {
    const result = await api.startRun(message, {
      model: composer.selectedModel.value,
      provider: composer.selectedProvider.value,
      reasoningEffort: composer.selectedReasoningEffort.value,
      workspace: context.selectedWorkspace.value,
      attachments: context.attachments.value.map(attachment => attachment.id)
    })
    composer.rememberLastUsedSelection()
    context.clearAttachments()
    clearDraft()
    playNotificationSound('sent')
    activeChatRuns.trackRun(result.sessionId, result.runId, { title: message })
    await router.push({ path: `/chat/${result.sessionId}`, query: { run: result.runId } })
    void refreshSessions?.()
  } catch (err) {
    showError(err, 'Failed to create chat')
  } finally {
    loading.value = false
  }
}

</script>

<template>
  <UDashboardPanel>
    <template #header>
      <AppNavbar
        title="New chat"
      />
    </template>

    <template #body>
      <UContainer class="flex min-h-full items-center justify-center py-12">
        <div class="w-full max-w-3xl space-y-6">
          <div class="space-y-2 text-center">
            <h1 class="text-3xl font-semibold tracking-tight">How can Hermes help?</h1>
            <p class="text-muted">Start a native web chat session backed by Hermes Agent.</p>
          </div>

          <div
            class="relative rounded-xl"
            :class="isDraggingFiles ? 'ring-2 ring-primary/40 ring-offset-2 ring-offset-default' : undefined"
            @dragenter="onPromptDragEnter"
            @dragover="onPromptDragOver"
            @dragleave="onPromptDragLeave"
            @drop="onPromptDrop"
          >
            <UChatPrompt
              v-model="input"
              :error="error || context.contextError.value"
              @submit="onSubmit"
              @paste="onPromptPaste"
              @keydown.down="onPromptArrowDown"
              @keydown.up="onPromptArrowUp"
              @keydown.esc="onPromptEscape"
              @keydown.enter="onPromptAutocompleteEnter"
            >
              <template #footer>
                <ChatPromptFooter
                  :submit-status="loading ? 'submitted' : 'ready'"
                  :workspaces="context.workspaces.value"
                  :selected-workspace="context.selectedWorkspace.value"
                  :workspace-invalid-signal="workspaceInvalidSignal"
                  :workspaces-loading="context.workspacesLoading.value"
                  :attachments="context.attachments.value"
                  :attachments-loading="context.attachmentsLoading.value"
                  :models="composer.models.value"
                  :selected-model="composer.selectedModel.value"
                  :selected-provider="composer.selectedProvider.value"
                  :selected-reasoning-effort="composer.selectedReasoningEffort.value"
                  :capabilities-loading="composer.capabilitiesLoading.value"
                  :slash-commands="slashCommands.filteredCommands.value"
                  :slash-commands-open="slashCommands.isOpen.value"
                  :slash-commands-loading="slashCommands.loading.value"
                  :highlighted-slash-command-index="slashCommands.highlightedIndex.value"
                  @update-selected-workspace="context.selectWorkspace"
                  @attach-files="attachFiles"
                  @remove-attachment="context.removeAttachment"
                  @voice-text="appendVoiceText"
                  @voice-error="showVoiceError"
                  @update-selected-model="composer.selectedModel.value = $event"
                  @update-selected-provider="composer.selectedProvider.value = $event"
                  @update-selected-reasoning-effort="composer.selectedReasoningEffort.value = $event"
                  @select-slash-command="selectSlashCommand"
                  @highlight-slash-command="slashCommands.highlightedIndex.value = $event"
                />
              </template>
            </UChatPrompt>
            <div class="mt-2 flex justify-start">
              <ProviderUsageBadge
                display="text"
                :usage="providerUsage.usage.value"
                :loading="providerUsage.loading.value"
              />
            </div>
            <div
              v-if="isDraggingFiles"
              class="pointer-events-none absolute inset-0 z-20 flex items-center justify-center rounded-xl border border-dashed border-primary/50 bg-primary/10 text-sm font-medium text-highlighted backdrop-blur-sm"
            >
              Drop files to attach
            </div>
          </div>
        </div>
      </UContainer>
    </template>
  </UDashboardPanel>
</template>
