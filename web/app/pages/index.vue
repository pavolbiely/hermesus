<script setup lang="ts">
import { NEW_CHAT_DRAFT_ID } from '~/utils/chatDrafts'

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

const workspaceItems = computed(() => context.workspaces.value.map(workspace => ({
  label: workspace.label,
  value: workspace.path
})))
const workspaceLabel = computed(() => {
  const selected = context.selectedWorkspace.value
  if (!selected) return 'Workspace'
  return context.workspaces.value.find(workspace => workspace.path === selected)?.label || selected
})

onMounted(() => {
  void initializeComposer()
})

async function initializeComposer() {
  try {
    await context.initialize()
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
  input.value = input.value ? `${input.value.trimEnd()} ${text}` : text
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
    const result = await acp.createSession({ cwd: context.selectedWorkspace.value })
    pendingAcpPrompts.value[result.sessionId] = { message, attachments }
    clearDraft()
    context.clearAttachments()
    await router.push({ path: `/acp/${result.sessionId}` })
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

          <div class="relative rounded-xl">
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
                  @attach-files="attachFiles"
                  @remove-attachment="context.removeAttachment"
                  @voice-text="appendVoiceText"
                  @voice-error="showVoiceError"
                  @update-selected-workspace="context.selectWorkspace"
                />
              </template>
            </UChatPrompt>
          </div>
        </div>
      </UContainer>
    </template>
  </UDashboardPanel>
</template>
