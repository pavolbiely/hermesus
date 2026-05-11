<script setup lang="ts">
import type { SessionConfigOption, SessionModelState } from '~/types/acp-api'
import { NEW_CHAT_DRAFT_ID } from '~/utils/chatDrafts'
import { filesFromClipboard } from '~/utils/clipboard'

const { input, clearDraft } = useChatDraft(NEW_CHAT_DRAFT_ID)
const loading = ref(false)
const error = ref<Error | undefined>()
const workspaceInvalidSignal = ref(0)
const acp = useAcpApi()
const pendingAcpPrompts = usePendingAcpPrompt()
const router = useRouter()
const refreshSessions = inject<() => Promise<void> | void>('refreshSessions')
const CHAT_PROMPT_MAX_ROWS = 6
const context = useChatComposerContext()
const newChatRequest = useNewChatRequest()
const toast = useToast()
const spellcheck = useChatInputSpellcheck()
const draftSessionId = ref<string | null>(null)
const draftSessionConsumed = ref(false)
const modelState = ref<SessionModelState | null>(null)
const configOptions = ref<SessionConfigOption[]>([])
const updatingSessionConfig = ref(false)
const promptContainer = ref<HTMLElement | null>(null)

const workspaceItems = computed(() => context.workspaces.value.map(workspace => ({
  label: workspace.label,
  value: workspace.path
})))
const workspaceLabel = computed(() => {
  const selected = context.selectedWorkspace.value
  if (!selected) return 'Workspace'
  return context.workspaces.value.find(workspace => workspace.path === selected)?.label || selected
})
const selectedModelId = computed(() => modelState.value?.currentModelId || undefined)
const modelItems = computed(() => modelState.value?.availableModels.map(model => ({
  label: model.name,
  value: model.modelId
})) || [])
const reasoningConfigOption = computed(() => {
  return configOptions.value.find((option) => {
    if (option.type !== 'select') return false
    const haystack = `${option.category || ''} ${option.id} ${option.name}`.toLowerCase()
    return option.category === 'thought_level' || haystack.includes('reasoning') || haystack.includes('thought')
  }) || null
})
const reasoningItems = computed(() => {
  const option = reasoningConfigOption.value
  return option ? [...configOptionItems(option)].reverse() : []
})
const selectedReasoningId = computed(() => {
  const value = reasoningConfigOption.value?.currentValue
  return typeof value === 'string' && value ? value : undefined
})
const selectedModelLabel = computed(() => selectedModelId.value ? modelItems.value.find(item => item.value === selectedModelId.value)?.label : 'Model')
const selectedReasoningLabel = computed(() => selectedReasoningId.value ? reasoningItems.value.find(item => item.value === selectedReasoningId.value)?.label : 'Reasoning')
const canAttachPastedFiles = computed(() => !loading.value && !context.attachmentsLoading.value)

onMounted(() => {
  promptContainer.value?.addEventListener('paste', onPaste)
  void initializeComposer()
})

onBeforeUnmount(() => {
  promptContainer.value?.removeEventListener('paste', onPaste)
  if (draftSessionId.value && !draftSessionConsumed.value) {
    void acp.closeSession(draftSessionId.value).catch(() => {})
  }
})

async function initializeComposer() {
  try {
    await context.initialize()
    await ensureDraftSession()
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
    void resetDraftSession().catch(err => showError(err, 'Could not initialize new chat'))
  },
  { immediate: true }
)

function appendVoiceText(text: string) {
  input.value = input.value ? `${input.value.trimEnd()} ${text}` : text
}

function configOptionItems(option: SessionConfigOption) {
  if (option.type !== 'select') return []
  return option.options.flatMap((item) => {
    if ('options' in item) {
      return item.options
        .filter(child => isSupportedReasoningOption(option, child.value))
        .map(child => ({ label: `${item.name}: ${child.name}`, value: child.value }))
    }
    return isSupportedReasoningOption(option, item.value) ? [{ label: item.name, value: item.value }] : []
  })
}

function isSupportedReasoningOption(option: SessionConfigOption, value: string) {
  if (option.id !== 'reasoning_effort') return true
  return value !== 'none' && value !== 'minimal'
}

async function ensureDraftSession() {
  if (draftSessionId.value) return draftSessionId.value

  updatingSessionConfig.value = true
  try {
    const result = await acp.createSession({ cwd: context.selectedWorkspace.value })
    draftSessionId.value = result.sessionId
    draftSessionConsumed.value = false
    modelState.value = result.models || null
    configOptions.value = result.configOptions || []
    return result.sessionId
  } finally {
    updatingSessionConfig.value = false
  }
}

async function resetDraftSession() {
  const previousSessionId = draftSessionId.value
  draftSessionId.value = null
  modelState.value = null
  configOptions.value = []
  if (previousSessionId && !draftSessionConsumed.value) {
    await acp.closeSession(previousSessionId).catch(() => {})
  }
  draftSessionConsumed.value = false
  await ensureDraftSession()
}

async function updateWorkspace(path: string | null) {
  context.selectWorkspace(path)
  try {
    await resetDraftSession()
  } catch (err) {
    showError(err, 'Could not initialize new chat')
  }
}

async function updateSessionModel(modelId: string) {
  if (modelId === modelState.value?.currentModelId) return
  updatingSessionConfig.value = true
  try {
    const sessionId = await ensureDraftSession()
    await acp.setSessionModel(sessionId, modelId)
    if (modelState.value) modelState.value = { ...modelState.value, currentModelId: modelId }
  } catch (err) {
    showError(err, 'Failed to update ACP model')
  } finally {
    updatingSessionConfig.value = false
  }
}

async function updateSessionReasoning(value: string) {
  const option = reasoningConfigOption.value
  if (!option || value === option.currentValue) return
  updatingSessionConfig.value = true
  try {
    const sessionId = await ensureDraftSession()
    const result = await acp.setSessionConfigOption(sessionId, option.id, { value })
    configOptions.value = result.configOptions.length
      ? result.configOptions
      : configOptions.value.map((item) => {
          if (item.id !== option.id || item.type !== 'select') return item
          return { ...item, currentValue: value }
        })
  } catch (err) {
    showError(err, `Failed to update ${option.name}`)
  } finally {
    updatingSessionConfig.value = false
  }
}

function showVoiceError(message: string) {
  toast.add({ color: 'error', title: 'Voice input failed', description: message })
}

async function attachFiles(files: File[]) {
  try {
    await context.uploadFiles(files)
  } catch (err) {
    showError(err, 'Failed to attach files')
  }
}

function onPaste(event: ClipboardEvent) {
  const files = filesFromClipboard(event)
  if (!files.length) return

  event.preventDefault()
  if (canAttachPastedFiles.value) void attachFiles(files)
}

function showError(err: unknown, fallback: string) {
  const message = getHermesErrorMessage(err, fallback)
  error.value = new Error(message)
  toast.add({ color: 'error', title: fallback, description: message })
}

async function onSubmit() {
  const message = input.value.trim()
  if ((!message && !context.attachments.value.length) || loading.value) return
  const attachments = context.attachments.value
  loading.value = true
  error.value = undefined
  try {
    const existingSessionId = await ensureDraftSession()
    pendingAcpPrompts.value[existingSessionId] = { message, attachments }
    draftSessionConsumed.value = true
    clearDraft()
    context.clearAttachments()
    await router.push({ path: `/acp/${existingSessionId}` })
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

          <div ref="promptContainer" class="relative rounded-xl">
            <UChatPrompt
              v-model="input"
              :maxrows="CHAT_PROMPT_MAX_ROWS"
              :spellcheck="spellcheck.spellcheck.value"
              :lang="spellcheck.lang.value"
              @submit="onSubmit"
            >
              <template #footer>
                <AcpChatPromptFooter
                  :submit-status="loading ? 'submitted' : 'ready'"
                  :submit-disabled="!input.trim() && !context.attachments.value.length"
                  :attachments="context.attachments.value"
                  :attachments-loading="context.attachmentsLoading.value"
                  :workspaces="workspaceItems"
                  :selected-workspace="context.selectedWorkspace.value"
                  :workspaces-loading="context.workspacesLoading.value"
                  :workspace-label="workspaceLabel"
                  :models="modelItems"
                  :selected-model="selectedModelId"
                  :model-label="selectedModelLabel || 'Model'"
                  :modes="reasoningItems"
                  :selected-mode="selectedReasoningId"
                  :reasoning-label="selectedReasoningLabel || 'Reasoning'"
                  :updating-session-config="updatingSessionConfig"
                  @attach-files="attachFiles"
                  @remove-attachment="context.removeAttachment"
                  @voice-text="appendVoiceText"
                  @voice-error="showVoiceError"
                  @update-selected-workspace="updateWorkspace"
                  @update-selected-model="updateSessionModel"
                  @update-selected-mode="updateSessionReasoning"
                />
              </template>
            </UChatPrompt>
          </div>
        </div>
      </UContainer>
    </template>
  </UDashboardPanel>
</template>
