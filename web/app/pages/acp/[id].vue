<script setup lang="ts">
import type { PlanEntry } from '@agentclientprotocol/sdk'
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
import { isAcpPlanUpdate, normalizeAcpPlanEntries } from '~/utils/acpPlanNormalization'
import { toolCallTitle } from '~/utils/toolCalls'

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
const planEntries = ref<PlanEntry[]>([])
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
const displayMessages = computed(() => groupProcessMessages(messages.value))
const activeRunMessage = computed(() => {
  if (!activePromptTurnId.value) return null
  return [...displayMessages.value].reverse().find(message => message.turnId === activePromptTurnId.value && hasRunDetails(message)) || null
})
const currentActivityLabel = computed(() => {
  const activeMessage = activeRunMessage.value
  if (!activePromptTurnId.value) return null
  if (!activeMessage) return 'Starting…'
  return runActivityLabel(activeMessage) || 'Working…'
})
const showRunActivityIndicator = computed(() => Boolean(currentActivityLabel.value))
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
const reasoningConfigOption = computed(() => {
  return configOptions.value.find((option) => {
    if (option.type !== 'select') return false
    const haystack = `${option.category || ''} ${option.id} ${option.name}`.toLowerCase()
    return option.category === 'thought_level' || haystack.includes('reasoning') || haystack.includes('thought')
  }) || null
})
const reasoningItems = computed(() => {
  const option = reasoningConfigOption.value
  return option ? configOptionItems(option) : modeItems.value
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
const selectedReasoningId = computed(() => {
  const value = reasoningConfigOption.value?.currentValue ?? selectedModeId.value
  return typeof value === 'string' && value ? value : undefined
})
const selectedModeLabel = computed(() => selectedReasoningId.value ? reasoningItems.value.find(item => item.value === selectedReasoningId.value)?.label : 'Reasoning')
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
  planEntries.value = []
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
    if (isAcpPlanUpdate(update)) {
      planEntries.value = normalizeAcpPlanEntries(update.entries)
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

function groupProcessMessages(source: AcpChatMessage[]): AcpChatMessage[] {
  const grouped: AcpChatMessage[] = []

  for (const message of source) {
    const clone = cloneChatMessage(message)
    const previous = grouped[grouped.length - 1]
    if (previous && shouldMergeAssistantProcessMessage(previous, clone)) {
      previous.parts.push(...clone.parts)
      previous.id = `${previous.id}:${clone.id}`
      continue
    }
    grouped.push(clone)
  }

  return grouped
}

function shouldMergeAssistantProcessMessage(previous: AcpChatMessage, next: AcpChatMessage) {
  if (previous.role !== 'assistant' || next.role !== 'assistant') return false
  if (hasTextParts(previous) || hasTextParts(next)) return false
  return hasProcessParts(previous) && hasProcessParts(next)
}

function cloneChatMessage(message: AcpChatMessage): AcpChatMessage {
  return {
    ...message,
    parts: message.parts.map(part => ({ ...part }))
  }
}

function hasTextParts(message: AcpChatMessage) {
  return message.parts.some(part => part.type === 'text' && part.text.trim())
}

function hasProcessParts(message: AcpChatMessage) {
  return message.parts.some(part => part.type === 'tool' || part.type === 'reasoning' || part.type === 'event')
}

function reasoningText(message: AcpChatMessage) {
  return message.parts.filter(part => part.type === 'reasoning').map(part => part.text).join('')
}

function toolParts(message: AcpChatMessage): AcpToolPart[] {
  return message.parts.filter((part): part is AcpToolPart => part.type === 'tool')
}

function runDetailSummary(message: AcpChatMessage) {
  const tools = toolParts(message)
  const failed = tools.filter(part => part.error || part.status === 'failed').length
  const running = runningToolParts(message).length
  const completed = tools.length - failed - running
  const parts: string[] = []
  if (running) parts.push(`${running} running`)
  if (completed) parts.push(`${completed} completed`)
  if (failed) parts.push(`${failed} failed`)
  return parts.join(' · ')
}

function runningToolParts(message: AcpChatMessage) {
  return toolParts(message).filter(part => part.state !== 'completed' && !part.error)
}

function runActivityLabel(message: AcpChatMessage) {
  const runningTool = runningToolParts(message)[0]
  if (runningTool) return `Running ${toolCallTitle(runningTool)}`
  if (message.turnId && message.turnId === activePromptTurnId.value && reasoningText(message).trim()) return 'Thinking'
  return ''
}

function hasRunDetails(message: AcpChatMessage) {
  return toolParts(message).length > 0 || Boolean(reasoningText(message))
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
  const option = reasoningConfigOption.value
  if (option) {
    await updateConfigOption(option, modeId)
    return
  }
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
    if (result.configOptions.length) {
      configOptions.value = result.configOptions
    } else {
      configOptions.value = configOptions.value.map((item) => {
        if (item.id !== option.id) return item
        return item.type === 'boolean'
          ? { ...item, currentValue: Boolean(value) }
          : { ...item, currentValue: String(value) }
      })
    }
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

            <AcpPlanCard
              v-if="planEntries.length"
              :entries="planEntries"
            />

            <UChatMessages
              v-if="!loading || messages.length"
              :messages="displayMessages"
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
                  <details
                    v-if="hasRunDetails(message)"
                    class="group/run-details rounded-lg border border-default bg-muted/20 text-sm"
                  >
                    <summary
                      class="flex w-full cursor-pointer list-none items-center gap-2 overflow-hidden px-3 py-2 text-left text-muted transition-colors hover:text-default [&::-webkit-details-marker]:hidden"
                    >
                      <UIcon
                        name="i-lucide-chevron-right"
                        class="size-3.5 shrink-0 text-dimmed transition-transform group-open/run-details:rotate-90"
                      />
                      <UIcon
                        :name="toolParts(message).some(part => part.error) ? 'i-lucide-circle-alert' : 'i-lucide-list-tree'"
                        class="size-3.5 shrink-0"
                        :class="toolParts(message).some(part => part.error) ? 'text-error' : 'text-dimmed'"
                      />
                      <span class="shrink-0 font-medium text-toned">Run details</span>
                      <span v-if="runDetailSummary(message)" class="min-w-0 truncate text-dimmed">
                        {{ runDetailSummary(message) }}
                      </span>
                    </summary>

                    <div class="space-y-2 border-t border-default px-3 py-2">
                      <UChatReasoning
                        v-if="reasoningText(message)"
                        :text="reasoningText(message)"
                        :ui="{ body: 'max-h-[200px] pt-1 overflow-y-auto text-sm text-dimmed whitespace-pre-wrap' }"
                      />

                      <AcpToolCallItem
                        v-for="part in toolParts(message)"
                        :key="part.toolCallId"
                        :part="part"
                      />
                    </div>
                  </details>
                </div>
              </template>
            </UChatMessages>

            <UChatMessage
              v-if="showRunActivityIndicator"
              id="run-activity-indicator"
              role="assistant"
              variant="naked"
              :parts="[]"
              class="px-2.5"
            >
              <template #content>
                <AcpRunActivityIndicator :label="currentActivityLabel || 'Working…'" />
              </template>
            </UChatMessage>
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
                  :modes="reasoningItems"
                  :selected-mode="selectedReasoningId"
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
