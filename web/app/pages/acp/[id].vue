<script setup lang="ts">
import type {
  AvailableCommand,
  PermissionOption,
  RequestPermissionRequest,
  SessionConfigOption,
  SessionModeState,
  SessionModelState
} from '~/types/acp-api'
import type { AcpChatMessage } from '~/types/acp-chat'
import type { ChatPromptAttachment, SlashCommand } from '~/types/chat'
import { formatDetailValue, valueSummary } from '~/utils/toolCallDetails'

type PendingPermission = {
  appRequestId: string
  request: RequestPermissionRequest
}

type AcpToolPart = Extract<AcpChatMessage['parts'][number], { type: 'tool' }>

const route = useRoute()
const router = useRouter()
const api = useAcpApi()
const context = useChatComposerContext()
const pendingAcpPrompts = usePendingAcpPrompt()
const transcript = useAcpTranscript()
const toast = useToast()

const sessionId = computed(() => String(route.params.id || ''))
const input = ref('')
const loading = ref(true)
const activePromptTurnId = ref<string | null>(null)
const pendingPermissions = ref<PendingPermission[]>([])
const modelState = ref<SessionModelState | null>(null)
const modeState = ref<SessionModeState | null>(null)
const configOptions = ref<SessionConfigOption[]>([])
const availableCommands = ref<AvailableCommand[]>([])
const updatingSessionConfig = ref(false)
const error = ref<string | null>(null)
let closeEvents: (() => void) | undefined
let eventSource: EventSource | undefined

const submitting = computed(() => Boolean(activePromptTurnId.value))
const submitStatus = computed(() => submitting.value ? 'streaming' : 'ready')
const messages = computed(() => transcript.messages.value)
const selectedModelId = computed({
  get: () => modelState.value?.currentModelId || undefined,
  set: (modelId: string | undefined) => {
    if (modelId) void updateSessionModel(modelId)
  }
})
const selectedModeId = computed({
  get: () => modeState.value?.currentModeId || undefined,
  set: (modeId: string | undefined) => {
    if (modeId) void updateSessionMode(modeId)
  }
})
const modelItems = computed(() => {
  return modelState.value?.availableModels.map(model => ({
    label: model.name,
    value: model.modelId
  })) || []
})
const modeItems = computed(() => {
  return modeState.value?.availableModes.map(mode => ({
    label: mode.name,
    value: mode.id
  })) || []
})
const workspaceItems = computed(() => context.workspaces.value.map(workspace => ({
  label: workspace.label,
  value: workspace.path
})))
const workspaceLabel = computed(() => {
  const selected = context.selectedWorkspace.value
  if (!selected) return 'Workspace'
  return context.workspaces.value.find(workspace => workspace.path === selected)?.label || selected
})
const selectedModelLabel = computed(() => selectedModelId.value ? modelItems.value.find(item => item.value === selectedModelId.value)?.label : 'Model')
const selectedModeLabel = computed(() => selectedModeId.value ? modeItems.value.find(item => item.value === selectedModeId.value)?.label : 'Reasoning')
const visibleConfigOptions = computed(() => configOptions.value.filter(option => option.type === 'select' || option.type === 'boolean'))
const hasSessionControls = computed(() => Boolean(modelItems.value.length || modeItems.value.length || visibleConfigOptions.value.length))
const slashCommandItems = computed<SlashCommand[]>(() => availableCommands.value.map(command => ({
  id: command.name,
  name: `/${command.name}`,
  usage: `/${command.name}${command.input ? ' …' : ''}`,
  description: command.description,
  safety: 'safe'
})))
const slashCommands = useStaticSlashCommands({ input, commands: slashCommandItems })
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

onMounted(async () => {
  await Promise.all([context.initialize(), initializeSession()])
})

onBeforeUnmount(() => {
  closeEvents?.()
})

watch(sessionId, async () => {
  await initializeSession()
})

async function initializeSession() {
  if (!sessionId.value) return
  loading.value = true
  error.value = null
  transcript.reset()
  pendingPermissions.value = []
  modelState.value = null
  modeState.value = null
  configOptions.value = []
  availableCommands.value = []
  closeEvents?.()
  activePromptTurnId.value = null
  try {
    const loaded = await api.loadSession(sessionId.value)
    modelState.value = loaded.models || null
    modeState.value = loaded.modes || null
    configOptions.value = loaded.configOptions || []
    loaded.events.forEach(handleBridgeEvent)
    eventSource = api.subscribeSession(sessionId.value, handleBridgeEvent, () => {
      error.value ||= 'ACP event stream disconnected.'
    })
    closeEvents = () => eventSource?.close()

    const queuedPrompt = pendingAcpPrompts.value[sessionId.value]
    if (queuedPrompt) {
      delete pendingAcpPrompts.value[sessionId.value]
      await router.replace({ path: route.path, query: {} })
      await sendPrompt(queuedPrompt.message, queuedPrompt.attachments)
      return
    }

    const queuedPromptText = typeof route.query.prompt === 'string' ? route.query.prompt : ''
    if (queuedPromptText.trim()) {
      await router.replace({ path: route.path, query: {} })
      await sendPrompt(queuedPromptText)
    }
  } catch (err) {
    showError(err, 'Could not load ACP session')
  } finally {
    loading.value = false
  }
}

async function onSubmit() {
  const message = input.value.trim()
  if ((!message && !context.attachments.value.length) || submitting.value) return
  const attachments = context.attachments.value
  input.value = ''
  context.clearAttachments()
  await sendPrompt(message, attachments)
}

async function sendPrompt(message: string, attachments: ChatPromptAttachment[] = []) {
  error.value = null
  const turnId = crypto.randomUUID()
  const messageId = crypto.randomUUID()
  activePromptTurnId.value = turnId
  transcript.applyEvent({
    type: 'user.message',
    eventId: `optimistic-user:${turnId}`,
    sessionId: sessionId.value,
    turnId,
    messageId,
    text: message,
    occurredAt: new Date().toISOString()
  })

  try {
    await api.startPrompt(sessionId.value, {
      prompt: attachmentsToPromptBlocks(message || 'See attached files.', attachments),
      turnId,
      messageId
    })
  } catch (err) {
    if (activePromptTurnId.value === turnId) activePromptTurnId.value = null
    showError(err, 'Failed to send prompt')
  }
}

async function stopPrompt() {
  if (!submitting.value) return
  try {
    await api.cancel(sessionId.value)
  } catch (err) {
    showError(err, 'Failed to cancel prompt')
  } finally {
    activePromptTurnId.value = null
  }
}

function handleBridgeEvent(event: Parameters<typeof transcript.applyBridgeEvent>[0]) {
  transcript.applyBridgeEvent(event)
  if (event.type === 'permission.requested') {
    pendingPermissions.value = [
      ...pendingPermissions.value.filter(item => item.appRequestId !== event.appRequestId),
      { appRequestId: event.appRequestId, request: event.request }
    ]
  }
  if (event.type === 'permission.resolved') {
    pendingPermissions.value = pendingPermissions.value.filter(item => item.appRequestId !== event.appRequestId)
  }
  if (event.type === 'session.update') {
    const update = event.notification.update
    if (update.sessionUpdate === 'current_mode_update' && modeState.value) {
      modeState.value = { ...modeState.value, currentModeId: update.currentModeId }
    }
    if (update.sessionUpdate === 'config_option_update') {
      configOptions.value = update.configOptions
    }
    if (update.sessionUpdate === 'available_commands_update') {
      availableCommands.value = update.availableCommands
    }
  }
  if (
    event.type === 'prompt.completed'
    || event.type === 'prompt.failed'
    || event.type === 'prompt.cancelled'
  ) {
    if (!('turnId' in event) || event.turnId === activePromptTurnId.value) {
      activePromptTurnId.value = null
    }
  }
}

function showError(err: unknown, fallback: string) {
  const message = err instanceof Error ? err.message : String(err || fallback)
  error.value = message
  toast.add({ color: 'error', title: fallback, description: message })
}

async function respondToPermission(appRequestId: string, option?: PermissionOption) {
  try {
    await api.respondToPermission(appRequestId, option ? { optionId: option.optionId } : { cancelled: true })
  } catch (err) {
    showError(err, 'Failed to respond to permission request')
  }
}

function partText(message: AcpChatMessage) {
  return message.parts.filter(part => part.type === 'text').map(part => part.text).join('')
}

function reasoningText(message: AcpChatMessage) {
  return message.parts.filter(part => part.type === 'reasoning').map(part => part.text).join('')
}

function toolParts(message: AcpChatMessage): AcpToolPart[] {
  return message.parts.filter((part): part is AcpToolPart => part.type === 'tool')
}

function toolLabel(part: AcpToolPart) {
  return friendlyToolName(part.name || part.toolCallId)
}

function toolSuffix(part: AcpToolPart) {
  if (part.error) return 'Failed'
  return part.state === 'completed' ? 'Completed' : 'Running'
}

function toolIcon(part: AcpToolPart) {
  const name = normalizedToolName(part.name)
  if (name.includes('terminal') || name.includes('shell') || name.includes('command')) return 'i-lucide-terminal'
  if (name.includes('search') || name.includes('grep')) return 'i-lucide-search'
  if (name.includes('read') || name.includes('file')) return 'i-lucide-file-text'
  if (name.includes('browser')) return 'i-lucide-globe'
  if (name.includes('skill')) return 'i-lucide-book-open'
  return 'i-lucide-wrench'
}

function toolSummary(part: AcpToolPart) {
  if (part.error) return part.error
  if (part.output !== undefined) return valueSummary(part.output)
  if (part.input !== undefined) return valueSummary(part.input)
  return part.state === 'completed' ? 'Finished' : 'Waiting for result…'
}

function acpToolDetailSections(part: AcpToolPart) {
  return [
    { label: 'Input', value: part.input },
    { label: 'Output', value: part.output }
  ].filter(section => section.value !== undefined && section.value !== null && section.value !== '')
}

function normalizedToolName(name: string) {
  return name.replace(/^functions\./, '').trim()
}

function friendlyToolName(name: string) {
  const normalized = normalizedToolName(name)
  const known: Record<string, string> = {
    terminal: 'Run terminal command',
    execute: 'Run command',
    search: 'Search files',
    read: 'Read file',
    search_files: 'Search files',
    read_file: 'Read file',
    write_file: 'Write file',
    patch: 'Edit file',
    browser_navigate: 'Open browser',
    browser_click: 'Click browser element',
    browser_snapshot: 'Inspect browser page',
    browser_console: 'Inspect browser console',
    skill_view: 'Load skill',
    delegate_task: 'Delegate task'
  }
  if (known[normalized]) return known[normalized]
  return normalized
    .replace(/^mcp_/, '')
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/^./, char => char.toUpperCase())
}

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

function permissionTitle(permission: PendingPermission) {
  const toolCall = permission.request.toolCall as Record<string, unknown>
  const value = toolCall.title ?? toolCall.name ?? toolCall.kind ?? toolCall.toolCallId
  return typeof value === 'string' && value ? value : 'Permission required'
}

function configOptionItems(option: SessionConfigOption) {
  if (option.type !== 'select') return []
  return option.options.flatMap((item) => {
    if ('options' in item) {
      return item.options.map(child => ({ label: `${item.name}: ${child.name}`, value: child.value }))
    }
    return [{ label: item.name, value: item.value }]
  })
}

async function updateSessionMode(modeId: string) {
  if (modeId === modeState.value?.currentModeId) return
  updatingSessionConfig.value = true
  try {
    await api.setSessionMode(sessionId.value, modeId)
    if (modeState.value) modeState.value = { ...modeState.value, currentModeId: modeId }
  } catch (err) {
    showError(err, 'Failed to update ACP mode')
  } finally {
    updatingSessionConfig.value = false
  }
}

async function updateSessionModel(modelId: string) {
  if (modelId === modelState.value?.currentModelId) return
  updatingSessionConfig.value = true
  try {
    await api.setSessionModel(sessionId.value, modelId)
    if (modelState.value) modelState.value = { ...modelState.value, currentModelId: modelId }
  } catch (err) {
    showError(err, 'Failed to update ACP model')
  } finally {
    updatingSessionConfig.value = false
  }
}

async function updateConfigOption(option: SessionConfigOption, value: boolean | string) {
  if (value === option.currentValue) return
  updatingSessionConfig.value = true
  try {
    const result = await api.setSessionConfigOption(
      sessionId.value,
      option.id,
      option.type === 'boolean' ? { type: 'boolean', value: Boolean(value) } : { value: String(value) }
    )
    configOptions.value = result.configOptions
  } catch (err) {
    showError(err, `Failed to update ${option.name}`)
  } finally {
    updatingSessionConfig.value = false
  }
}
</script>

<template>
  <UDashboardPanel>
    <template #header>
      <AppNavbar title="ACP chat" />
    </template>

    <template #body>
      <div class="flex h-full min-h-0 flex-col">
        <div class="min-h-0 flex-1 overflow-y-auto px-4 py-6">
          <div class="mx-auto w-full max-w-3xl space-y-4">
            <UAlert
              v-if="error"
              color="error"
              variant="soft"
              title="ACP chat error"
              :description="error"
            />

            <div v-if="loading && !messages.length" class="space-y-4" aria-label="Loading ACP session">
              <USkeleton class="h-16 w-4/5 rounded-2xl" />
              <USkeleton class="ml-auto h-10 w-2/5 rounded-2xl" />
            </div>

            <UCard
              v-for="permission in pendingPermissions"
              :key="permission.appRequestId"
              variant="soft"
              :ui="{ body: 'space-y-3' }"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <p class="text-sm font-medium text-highlighted">{{ permissionTitle(permission) }}</p>
                  <p class="text-xs text-muted">Hermes is requesting permission before running this tool.</p>
                </div>
                <UBadge color="warning" variant="soft" size="sm">Permission</UBadge>
              </div>
              <div class="flex flex-wrap gap-2">
                <UButton
                  v-for="option in permission.request.options"
                  :key="option.optionId"
                  size="sm"
                  :color="option.kind.startsWith('allow') ? 'primary' : 'neutral'"
                  :variant="option.kind.startsWith('allow') ? 'solid' : 'soft'"
                  @click="respondToPermission(permission.appRequestId, option)"
                >
                  {{ option.name }}
                </UButton>
                <UButton
                  size="sm"
                  color="neutral"
                  variant="ghost"
                  @click="respondToPermission(permission.appRequestId)"
                >
                  Cancel
                </UButton>
              </div>
            </UCard>

            <UChatMessages
              v-if="!loading || messages.length"
              :messages="messages"
              :status="submitStatus"
              :auto-scroll="true"
            >
              <template #content="{ message }: { message: AcpChatMessage }">
                <div class="space-y-3">
                  <Comark
                    v-if="partText(message)"
                    :markdown="partText(message)"
                    class="prose prose-sm dark:prose-invert max-w-none"
                  />
                  <UChatReasoning
                    v-if="reasoningText(message)"
                    :text="reasoningText(message)"
                  />
                  <UChatTool
                    v-for="part in toolParts(message)"
                    :key="part.toolCallId"
                    :text="toolLabel(part)"
                    :suffix="toolSuffix(part)"
                    :icon="toolIcon(part)"
                    :loading="part.state !== 'completed' && !part.error"
                    :streaming="part.state !== 'completed' && !part.error"
                    chevron="leading"
                    variant="inline"
                    :ui="{ body: 'space-y-2 pt-1.5 text-xs text-dimmed' }"
                  >
                    <p
                      class="truncate text-xs"
                      :class="part.error ? 'text-error' : 'text-muted'"
                      :title="toolSummary(part)"
                    >
                      {{ toolSummary(part) }}
                    </p>
                    <div
                      v-for="section in acpToolDetailSections(part)"
                      :key="section.label"
                      class="space-y-1"
                    >
                      <p class="text-[11px] font-medium uppercase tracking-wide text-dimmed">{{ section.label }}</p>
                      <pre class="max-h-40 overflow-auto rounded-md bg-muted/40 p-2 text-[11px] leading-4 text-muted">{{ formatDetailValue(section.value) }}</pre>
                    </div>
                  </UChatTool>
                </div>
              </template>
            </UChatMessages>
          </div>
        </div>

        <div class="shrink-0 border-t border-default bg-default/80 px-4 py-4 backdrop-blur">
          <div class="mx-auto w-full max-w-3xl">
            <div class="relative">
              <ChatSlashCommandMenu
                :commands="slashCommands.filteredCommands.value"
                :open="slashCommands.isOpen.value"
                :loading="slashCommands.loading.value"
                :highlighted-index="slashCommands.highlightedIndex.value"
                @select="selectSlashCommand"
                @highlight="slashCommands.highlightedIndex.value = $event"
              />
              <UChatPrompt
                v-model="input"
                :maxrows="6"
                placeholder="Message Hermes through ACP…"
                @submit="onSubmit"
                @keydown.down="onPromptArrowDown"
                @keydown.up="onPromptArrowUp"
                @keydown.esc="onPromptEscape"
                @keydown.enter="onPromptAutocompleteEnter"
              >
              <template #footer>
                <AcpChatPromptFooter
                  :submit-status="submitStatus"
                  :submit-disabled="(!input.trim() && !context.attachments.value.length && !submitting)"
                  :attachments="context.attachments.value"
                  :attachments-loading="context.attachmentsLoading.value"
                  :workspaces="workspaceItems"
                  :selected-workspace="context.selectedWorkspace.value"
                  :workspaces-loading="context.workspacesLoading.value"
                  :workspace-label="workspaceLabel"
                  :models="modelItems"
                  :selected-model="selectedModelId"
                  :model-label="selectedModelLabel || 'Model'"
                  :modes="modeItems"
                  :selected-mode="selectedModeId"
                  :reasoning-label="selectedModeLabel || 'Reasoning'"
                  :updating-session-config="updatingSessionConfig"
                  @stop="stopPrompt"
                  @attach-files="attachFiles"
                  @remove-attachment="context.removeAttachment"
                  @voice-text="appendVoiceText"
                  @voice-error="showVoiceError"
                  @update-selected-workspace="context.selectWorkspace"
                  @update-selected-model="updateSessionModel"
                  @update-selected-mode="updateSessionMode"
                />
              </template>
              </UChatPrompt>
            </div>
          </div>
        </div>
      </div>
    </template>
  </UDashboardPanel>
</template>
