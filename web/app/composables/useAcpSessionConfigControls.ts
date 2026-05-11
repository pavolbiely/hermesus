import { computed, ref, type Ref } from 'vue'
import type {
  AvailableCommand,
  SessionConfigOption,
  SessionModeState,
  SessionModelState
} from '~/types/acp-api'
import type { AppWorkspace, SlashCommand } from '~/types/chat'

type ConfigControlItem = {
  label: string
  value: string
}

type UseAcpSessionConfigControlsOptions = {
  sessionId: Ref<string>
  workspaces: Ref<AppWorkspace[]>
  selectedWorkspace: Ref<string | null>
  api: {
    setSessionMode: (sessionId: string, modeId: string) => Promise<unknown>
    setSessionModel: (sessionId: string, modelId: string) => Promise<unknown>
    setSessionConfigOption: (
      sessionId: string,
      optionId: string,
      value: { type: 'boolean', value: boolean } | { value: string }
    ) => Promise<{ configOptions: SessionConfigOption[] }>
  }
  showError: (err: unknown, fallback: string) => void
}

export function useAcpSessionConfigControls(options: UseAcpSessionConfigControlsOptions) {
  const modelState = ref<SessionModelState | null>(null)
  const modeState = ref<SessionModeState | null>(null)
  const configOptions = ref<SessionConfigOption[]>([])
  const availableCommands = ref<AvailableCommand[]>([])
  const updatingSessionConfig = ref(false)

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

  const modelItems = computed<ConfigControlItem[]>(() => {
    return modelState.value?.availableModels.map(model => ({
      label: model.name,
      value: model.modelId
    })) || []
  })

  const modeItems = computed<ConfigControlItem[]>(() => {
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
    return [...(option ? configOptionItems(option) : modeItems.value)].reverse()
  })

  const workspaceItems = computed(() => options.workspaces.value.map(workspace => ({
    label: workspace.label,
    value: workspace.path
  })))

  const workspaceLabel = computed(() => {
    const selected = options.selectedWorkspace.value
    if (!selected) return 'Workspace'
    return options.workspaces.value.find(workspace => workspace.path === selected)?.label || selected
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

  async function updateSessionMode(modeId: string) {
    const option = reasoningConfigOption.value
    if (option) {
      await updateConfigOption(option, modeId)
      return
    }
    if (modeId === modeState.value?.currentModeId) return
    updatingSessionConfig.value = true
    try {
      await options.api.setSessionMode(options.sessionId.value, modeId)
      if (modeState.value) modeState.value = { ...modeState.value, currentModeId: modeId }
    } catch (err) {
      options.showError(err, 'Failed to update ACP mode')
    } finally {
      updatingSessionConfig.value = false
    }
  }

  async function updateSessionModel(modelId: string) {
    if (modelId === modelState.value?.currentModelId) return
    updatingSessionConfig.value = true
    try {
      await options.api.setSessionModel(options.sessionId.value, modelId)
      if (modelState.value) modelState.value = { ...modelState.value, currentModelId: modelId }
    } catch (err) {
      options.showError(err, 'Failed to update ACP model')
    } finally {
      updatingSessionConfig.value = false
    }
  }

  async function updateConfigOption(option: SessionConfigOption, value: boolean | string) {
    if (value === option.currentValue) return
    updatingSessionConfig.value = true
    try {
      const result = await options.api.setSessionConfigOption(
        options.sessionId.value,
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
      options.showError(err, `Failed to update ${option.name}`)
    } finally {
      updatingSessionConfig.value = false
    }
  }

  return {
    modelState,
    modeState,
    configOptions,
    availableCommands,
    updatingSessionConfig,
    selectedModelId,
    selectedModeId,
    modelItems,
    modeItems,
    reasoningConfigOption,
    reasoningItems,
    workspaceItems,
    workspaceLabel,
    selectedModelLabel,
    selectedReasoningId,
    selectedModeLabel,
    visibleConfigOptions,
    hasSessionControls,
    slashCommandItems,
    updateSessionMode,
    updateSessionModel,
    updateConfigOption
  }
}
