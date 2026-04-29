import type { MaybeRefOrGetter } from 'vue'
import type { WebChatProviderUsageResponse } from '~/types/web-chat'

const REFRESH_INTERVAL_MS = 5 * 60 * 1000

type ProviderUsageCacheEntry = {
  usage: WebChatProviderUsageResponse
  fetchedAt: number
}

const providerUsageCache = new Map<string, ProviderUsageCacheEntry>()
const providerUsageInFlight = new Map<string, Promise<WebChatProviderUsageResponse>>()

function providerUsageKey(provider: string, model: string | null) {
  return `${provider}\n${model || ''}`
}

function isFresh(entry: ProviderUsageCacheEntry, now = Date.now()) {
  return now - entry.fetchedAt < REFRESH_INTERVAL_MS
}

function unavailableUsage(provider: string | null, model: string | null, reason: string): WebChatProviderUsageResponse | null {
  if (!provider) return null
  return {
    provider,
    model,
    source: provider,
    available: false,
    unavailableReason: reason,
    limits: []
  }
}

export function useProviderUsage(
  provider: MaybeRefOrGetter<string | null | undefined>,
  model: MaybeRefOrGetter<string | null | undefined>
) {
  const api = useHermesApi()
  const usage = useState<WebChatProviderUsageResponse | null>('provider-usage', () => null)
  const loading = useState('provider-usage-loading', () => false)
  let requestId = 0
  let refreshInterval: ReturnType<typeof setInterval> | null = null

  async function refresh() {
    const nextProvider = toValue(provider)?.trim() || null
    const nextModel = toValue(model)?.trim() || null
    const currentRequest = ++requestId

    if (!nextProvider) {
      usage.value = null
      loading.value = false
      return
    }

    const key = providerUsageKey(nextProvider, nextModel)
    const cached = providerUsageCache.get(key)
    if (cached) usage.value = cached.usage
    if (cached && isFresh(cached)) {
      loading.value = false
      return
    }

    if (!cached) usage.value = null
    loading.value = true

    try {
      let request = providerUsageInFlight.get(key)
      if (!request) {
        request = api.getProviderUsage(nextProvider, nextModel)
        providerUsageInFlight.set(key, request)
      }

      const response = await request
      if (currentRequest !== requestId) return
      usage.value = response
      providerUsageCache.set(key, { usage: response, fetchedAt: Date.now() })
    } catch (err) {
      if (currentRequest !== requestId) return
      const response = unavailableUsage(
        nextProvider,
        nextModel,
        getHermesErrorMessage(err, 'Provider usage is unavailable.')
      )
      usage.value = response
      if (response) providerUsageCache.set(key, { usage: response, fetchedAt: Date.now() })
    } finally {
      providerUsageInFlight.delete(key)
      if (currentRequest === requestId) loading.value = false
    }
  }

  watch(
    () => [toValue(provider), toValue(model)] as const,
    () => { void refresh() },
    { immediate: true }
  )

  onMounted(() => {
    refreshInterval = setInterval(() => { void refresh() }, REFRESH_INTERVAL_MS)
  })

  onBeforeUnmount(() => {
    if (refreshInterval) clearInterval(refreshInterval)
  })

  return {
    usage,
    loading,
    refresh
  }
}
