import type { WebChatCapabilitiesResponse, WebChatModelCapability, WebChatSession } from '~/types/web-chat'
import type { ChatComposerSelection } from '~/utils/chatComposerSelections'
import { rememberChatComposerSelection, resolveSessionComposerSelection } from '~/utils/chatComposerSelections'

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
  const capabilitiesLoading = useState('chat-composer-capabilities-loading', () => false)
  const selectedModel = useState<string | null>('chat-composer-selected-model', () => null)
  const selectedProvider = useState<string | null>('chat-composer-selected-provider', () => null)
  const selectedReasoningEffort = useState<string | null>('chat-composer-selected-reasoning', () => null)
  const sessionSelections = useState<Record<string, ChatComposerSelection>>('chat-composer-session-selections', () => ({}))
  const lastUsedModel = useState<string | null>('chat-composer-last-used-model', () => null)
  const lastUsedProvider = useState<string | null>('chat-composer-last-used-provider', () => null)
  const lastUsedReasoningEffort = useState<string | null>('chat-composer-last-used-reasoning', () => null)

  const models = computed(() => capabilities.value?.models || [])
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

  function setSelection(modelId: string | null | undefined, reasoningEffort: string | null | undefined, providerId: string | null | undefined = selectedProvider.value) {
    const capability = normalizeModel(modelId, providerId)
    selectedModel.value = capability?.id || null
    selectedProvider.value = capability?.provider || normalizeProviderValue(providerId)
    selectedReasoningEffort.value = reconcileReasoning(selectedModel.value, reasoningEffort, selectedProvider.value)
  }

  async function ensureCapabilities() {
    if (capabilitiesLoading.value) return

    capabilitiesLoading.value = true
    try {
      capabilities.value = await api.getCapabilities()
    } finally {
      capabilitiesLoading.value = false
    }
  }

  async function initializeForNewChat() {
    await ensureCapabilities()
    setSelection(lastUsedModel.value, lastUsedReasoningEffort.value, lastUsedProvider.value)
  }

  function applySessionSelection(session: WebChatSession | null | undefined) {
    if (!session) {
      setSelection(null, null, null)
      return
    }

    const selection = resolveSessionComposerSelection(session, sessionSelections.value[session.id])
    setSelection(selection.model, selection.reasoningEffort, selection.provider)
  }

  async function initializeForSession(session: WebChatSession | null | undefined) {
    await ensureCapabilities()
    applySessionSelection(session)
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
    selectedReasoningEffort.value = reconcileReasoning(modelId, selectedReasoningEffort.value, providerId)
  })

  return {
    capabilities,
    capabilitiesLoading,
    defaultModel,
    defaultProvider,
    models,
    selectedModel,
    selectedProvider,
    selectedReasoningEffort,
    supportedReasoningEfforts,
    ensureCapabilities,
    initializeForNewChat,
    applySessionSelection,
    initializeForSession,
    rememberSessionSelection,
    rememberLastUsedSelection
  }
}
