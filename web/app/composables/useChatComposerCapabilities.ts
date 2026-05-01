import type { WebChatCapabilitiesResponse, WebChatModelCapability, WebChatSession } from '~/types/web-chat'
import type { ChatComposerSelection } from '~/utils/chatComposerSelections'
import { rememberChatComposerSelection, resolveSessionComposerSelection } from '~/utils/chatComposerSelections'

let capabilitiesRefreshPromise: Promise<void> | null = null

function normalizeReasoningValue(value: string | null | undefined) {
  const normalized = value?.trim().toLowerCase()
  return normalized || null
}

function normalizeProviderValue(value: string | null | undefined) {
  const normalized = value?.trim()
  return normalized || null
}

export function useChatComposerCapabilities() {
  const api = useHermesApi()

  const capabilities = useState<WebChatCapabilitiesResponse | null>('chat-composer-capabilities', () => null)
  const capabilitiesStatus = useState<'idle' | 'loading' | 'refreshing' | 'ready' | 'error'>('chat-composer-capabilities-status', () => 'idle')
  const capabilitiesError = useState<string | null>('chat-composer-capabilities-error', () => null)
  const capabilitiesFetchedAt = useState<number | null>('chat-composer-capabilities-fetched-at', () => null)
  const selectedModel = useState<string | null>('chat-composer-selected-model', () => null)
  const selectedProvider = useState<string | null>('chat-composer-selected-provider', () => null)
  const selectedReasoningEffort = useState<string | null>('chat-composer-selected-reasoning', () => null)
  const sessionSelections = useState<Record<string, ChatComposerSelection>>('chat-composer-session-selections', () => ({}))
  const lastUsedModel = useState<string | null>('chat-composer-last-used-model', () => null)
  const lastUsedProvider = useState<string | null>('chat-composer-last-used-provider', () => null)
  const lastUsedReasoningEffort = useState<string | null>('chat-composer-last-used-reasoning', () => null)

  const models = computed(() => capabilities.value?.models || [])
  const hasCapabilities = computed(() => models.value.length > 0)
  const capabilitiesLoading = computed(() => capabilitiesStatus.value === 'loading')
  const capabilitiesRefreshing = computed(() => capabilitiesStatus.value === 'refreshing')
  const defaultModel = computed(() => capabilities.value?.defaultModel || models.value[0]?.id || null)
  const defaultProvider = computed(() => capabilities.value?.defaultProvider || models.value[0]?.provider || null)

  function modelCapability(modelId: string | null | undefined, providerId: string | null | undefined = selectedProvider.value): WebChatModelCapability | null {
    if (!modelId) return null
    const normalizedProvider = normalizeProviderValue(providerId)
    return models.value.find(model => model.id === modelId && (!normalizedProvider || model.provider === normalizedProvider))
      || models.value.find(model => model.id === modelId)
      || null
  }

  function supportedReasoningEfforts(modelId: string | null | undefined, providerId: string | null | undefined = selectedProvider.value) {
    return modelCapability(modelId, providerId)?.reasoningEfforts || []
  }

  function defaultReasoningForModel(modelId: string | null | undefined, providerId: string | null | undefined = selectedProvider.value) {
    const capability = modelCapability(modelId, providerId)
    if (!capability) return null
    if (capability.defaultReasoningEffort) return capability.defaultReasoningEffort
    if (capability.reasoningEfforts.includes('medium')) return 'medium'
    return capability.reasoningEfforts[0] || null
  }

  function normalizeModel(modelId: string | null | undefined, providerId: string | null | undefined = selectedProvider.value) {
    const capability = modelCapability(modelId, providerId)
    if (capability) return capability
    return modelCapability(defaultModel.value, defaultProvider.value)
  }

  function reconcileReasoning(modelId: string | null | undefined, reasoningEffort: string | null | undefined, providerId: string | null | undefined = selectedProvider.value) {
    const supported = supportedReasoningEfforts(modelId, providerId)
    if (!supported.length) return null

    const normalized = normalizeReasoningValue(reasoningEffort)
    if (normalized && supported.includes(normalized)) return normalized

    return defaultReasoningForModel(modelId, providerId)
  }

  function setSelection(
    modelId: string | null | undefined,
    reasoningEffort: string | null | undefined,
    providerId: string | null | undefined = selectedProvider.value,
    options: { preserveUnknownModel?: boolean } = {}
  ) {
    const requestedModel = modelId?.trim() || null
    const requestedProvider = normalizeProviderValue(providerId)
    const requestedCapability = modelCapability(requestedModel, requestedProvider)
    if (requestedModel && !requestedCapability && options.preserveUnknownModel) {
      selectedModel.value = requestedModel
      selectedProvider.value = requestedProvider
      selectedReasoningEffort.value = normalizeReasoningValue(reasoningEffort)
      return
    }

    const capability = requestedCapability || normalizeModel(requestedModel, requestedProvider)
    selectedModel.value = capability?.id || requestedModel || null
    selectedProvider.value = capability?.provider || requestedProvider
    selectedReasoningEffort.value = capability
      ? reconcileReasoning(selectedModel.value, reasoningEffort, selectedProvider.value)
      : normalizeReasoningValue(reasoningEffort)
  }

  function applyLastUsedOrDefaultSelection() {
    setSelection(
      lastUsedModel.value || defaultModel.value,
      lastUsedReasoningEffort.value,
      lastUsedProvider.value || defaultProvider.value,
      { preserveUnknownModel: Boolean(lastUsedModel.value) }
    )
  }

  async function refreshCapabilities(options: { force?: boolean } = {}) {
    if (capabilitiesRefreshPromise) return capabilitiesRefreshPromise
    if (!options.force && capabilities.value && capabilitiesStatus.value === 'ready') return

    const hadCapabilities = hasCapabilities.value
    capabilitiesStatus.value = hadCapabilities ? 'refreshing' : 'loading'
    capabilitiesError.value = null

    capabilitiesRefreshPromise = api.getCapabilities()
      .then((next) => {
        capabilities.value = next
        capabilitiesFetchedAt.value = Date.now()
        capabilitiesStatus.value = 'ready'
        if (!selectedModel.value) applyLastUsedOrDefaultSelection()
      })
      .catch((err) => {
        capabilitiesError.value = getHermesErrorMessage(err, 'Could not load model capabilities')
        capabilitiesStatus.value = hadCapabilities ? 'ready' : 'error'
      })
      .finally(() => {
        capabilitiesRefreshPromise = null
      })

    return capabilitiesRefreshPromise
  }

  async function ensureCapabilities() {
    return refreshCapabilities({ force: true })
  }

  function initializeForNewChat() {
    applyLastUsedOrDefaultSelection()
    void refreshCapabilities()
  }

  function applySessionSelection(session: WebChatSession | null | undefined) {
    if (!session) {
      setSelection(null, null, null)
      return
    }

    const selection = resolveSessionComposerSelection(session, sessionSelections.value[session.id])
    setSelection(selection.model, selection.reasoningEffort, selection.provider, { preserveUnknownModel: true })
  }

  function initializeForSession(session: WebChatSession | null | undefined) {
    applySessionSelection(session)
    void refreshCapabilities()
  }

  function rememberSessionSelection(sessionId: string | null | undefined) {
    sessionSelections.value = rememberChatComposerSelection(sessionSelections.value, sessionId, {
      model: selectedModel.value,
      provider: selectedProvider.value,
      reasoningEffort: selectedReasoningEffort.value
    })
  }

  function rememberLastUsedSelection() {
    lastUsedModel.value = selectedModel.value
    lastUsedProvider.value = selectedProvider.value
    lastUsedReasoningEffort.value = selectedReasoningEffort.value
  }

  watch([selectedModel, selectedProvider], ([modelId, providerId]) => {
    if (!capabilities.value) return
    if (!modelCapability(modelId, providerId)) return
    selectedReasoningEffort.value = reconcileReasoning(modelId, selectedReasoningEffort.value, providerId)
  })

  return {
    capabilities,
    capabilitiesStatus,
    capabilitiesLoading,
    capabilitiesRefreshing,
    capabilitiesError,
    capabilitiesFetchedAt,
    defaultModel,
    defaultProvider,
    hasCapabilities,
    models,
    selectedModel,
    selectedProvider,
    selectedReasoningEffort,
    supportedReasoningEfforts,
    refreshCapabilities,
    ensureCapabilities,
    initializeForNewChat,
    applySessionSelection,
    initializeForSession,
    rememberSessionSelection,
    rememberLastUsedSelection
  }
}
