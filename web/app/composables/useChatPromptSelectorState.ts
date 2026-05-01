import type { DropdownMenuItem } from '@nuxt/ui'
import type { WebChatModelCapability, WebChatWorkspace } from '~/types/web-chat'

type ChatPromptSelectorProps = {
  workspaces: WebChatWorkspace[]
  selectedWorkspace?: string | null
  workspacesLoading: boolean
  models: WebChatModelCapability[]
  selectedModel?: string | null
  selectedProvider?: string | null
  selectedReasoningEffort?: string | null
  capabilitiesLoading: boolean
}

type ChatPromptSelectorEmit = {
  updateSelectedWorkspace: [path: string | null]
  updateSelectedModel: [model: string]
  updateSelectedProvider: [provider: string | null]
  updateSelectedReasoningEffort: [reasoningEffort: string]
}

export type ModelSelectItem = {
  label: string
  provider: string | null
  providerLabel: string
  model: WebChatModelCapability
}

export type ModelSelectGroup = {
  providerLabel: string
  items: ModelSelectItem[]
}

export function useChatPromptSelectorState(
  props: ChatPromptSelectorProps,
  emit: <K extends keyof ChatPromptSelectorEmit>(event: K, ...args: ChatPromptSelectorEmit[K]) => void
) {
  const modelPickerOpen = ref(false)
  const modelSearch = ref('')

  const selectedModelCapability = computed(() => {
    return props.models.find(model => model.id === props.selectedModel && (!props.selectedProvider || model.provider === props.selectedProvider))
      || props.models.find(model => model.id === props.selectedModel)
      || null
  })
  const reasoningEfforts = computed(() => selectedModelCapability.value?.reasoningEfforts || [])
  const selectedModelUnavailable = computed(() => {
    return Boolean(props.selectedModel && !props.capabilitiesLoading && !selectedModelCapability.value)
  })
  const selectedWorkspaceItem = computed(() => props.workspaces.find(workspace => workspace.path === props.selectedWorkspace) || null)
  const workspaceLabel = computed(() => selectedWorkspaceItem.value?.label || 'No workspace')
  const modelLabel = computed(() => selectedModelCapability.value?.label || props.selectedModel || 'Model')
  const reasoningLabel = computed(() => selectedModelUnavailable.value ? 'Unavailable' : (props.selectedReasoningEffort || 'Reasoning'))

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

  const modelGroups = computed<ModelSelectGroup[]>(() => {
    const groups = new Map<string, ModelSelectItem[]>()
    for (const model of props.models) {
      const providerLabel = model.providerLabel || model.provider || 'Other'
      const item: ModelSelectItem = {
        label: model.label,
        provider: model.provider || null,
        providerLabel,
        model
      }
      const group = groups.get(providerLabel) || []
      group.push(item)
      groups.set(providerLabel, group)
    }

    return Array.from(groups.entries()).map(([providerLabel, items]) => ({
      providerLabel,
      items: items.sort((a, b) => a.label.localeCompare(b.label))
    }))
  })

  const filteredModelGroups = computed<ModelSelectGroup[]>(() => {
    const query = modelSearch.value.trim().toLowerCase()
    if (!query) return modelGroups.value

    return modelGroups.value
      .map(group => ({
        providerLabel: group.providerLabel,
        items: group.items.filter(item => `${item.label} ${item.providerLabel}`.toLowerCase().includes(query))
      }))
      .filter(group => group.items.length > 0)
  })

  const hasModelItems = computed(() => modelGroups.value.some(group => group.items.length > 0))

  function selectModel(item: ModelSelectItem) {
    emit('updateSelectedModel', item.model.id)
    emit('updateSelectedProvider', item.provider)
    modelPickerOpen.value = false
    modelSearch.value = ''
  }

  const reasoningItems = computed<DropdownMenuItem[]>(() => reasoningEfforts.value.map(reasoningEffort => ({
    label: reasoningEffort,
    checked: reasoningEffort === props.selectedReasoningEffort,
    onSelect: () => emit('updateSelectedReasoningEffort', reasoningEffort),
    trailingIcon: reasoningEffort === props.selectedReasoningEffort ? 'i-lucide-check' : undefined
  })))

  return {
    modelPickerOpen,
    modelSearch,
    selectedModelCapability,
    selectedModelUnavailable,
    reasoningEfforts,
    selectedWorkspaceItem,
    workspaceLabel,
    modelLabel,
    reasoningLabel,
    workspaceItems,
    modelGroups,
    filteredModelGroups,
    hasModelItems,
    selectModel,
    reasoningItems
  }
}
