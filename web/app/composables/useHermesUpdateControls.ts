import type { WebChatAppUpdateStatusResponse, WebChatUpdateStatusResponse } from '~/types/web-chat'
import { launchUpdateFireworks } from '~/utils/updateFireworks'

const UPDATE_STATUS_CHECK_INTERVAL_MS = 20 * 60 * 1000

function formatUpdateCommitDate(value?: string | null) {
  if (!value) return null

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short'
  }).format(date)
}

export function useHermesUpdateControls() {
  const api = useHermesApi()
  const runtimeConfig = useRuntimeConfig()
  const toast = useToast()

  const updateStatus = useState<WebChatUpdateStatusResponse | null>('hermes-update-status', () => null)
  const updatePending = useState('hermes-update-pending', () => false)
  const updateCompleted = useState('hermes-update-completed', () => false)
  const appUpdateStatus = useState<WebChatAppUpdateStatusResponse | null>('hermes-app-update-status', () => null)
  const appUpdatePending = useState('hermes-app-update-pending', () => false)
  const appUpdateCompleted = useState('hermes-app-update-completed', () => false)

  let hideUpdateTimer: ReturnType<typeof setTimeout> | undefined
  let hideAppUpdateTimer: ReturnType<typeof setTimeout> | undefined
  let updateStatusTimer: ReturnType<typeof setInterval> | undefined
  let updateStatusCheckPending = false
  let lastUpdateStatusCheckAt = 0

  const updateNeeded = computed(() => Boolean(updateStatus.value?.updateAvailable || updateStatus.value?.runtimeOutOfSync))
  const showUpdateButton = computed(() => updatePending.value || updateCompleted.value || updateNeeded.value)
  const updateButtonLabel = computed(() => updateCompleted.value ? 'Hermes updated' : 'Update Hermes')
  const updateButtonColor = computed<'primary' | 'success'>(() => updateCompleted.value ? 'success' : 'primary')
  const updateButtonTitle = computed(() => {
    if (updateStatus.value?.updateAvailable && updateStatus.value?.runtimeOutOfSync) return 'Update Hermes Agent and sync runtime'
    if (updateStatus.value?.runtimeOutOfSync) return 'Sync Hermes runtime'
    return 'Update Hermes Agent'
  })
  const updateCommits = computed(() => (updateStatus.value?.commits ?? []).slice(0, 10).map(commit => ({
    ...commit,
    formattedCommittedAt: formatUpdateCommitDate(commit.committedAt)
  })))
  const updateRevisionSummary = computed(() => {
    const status = updateStatus.value
    if (!status?.currentRevision && !status?.remoteRevision && !status?.runtimeRevision) return ''

    const source = status.currentRevision || 'unknown'
    const remote = status.remoteRevision || 'unknown'
    const runtime = status.runtimeRevision || 'missing'
    return `${status.branch}: ${source} → ${remote}; runtime ${runtime}`
  })
  const updatePopoverMessage = computed(() => {
    if (updateStatus.value?.runtimeOutOfSync) return 'No remote commits are pending; this update will sync the disposable Hermes runtime.'
    return 'No commit details are available for this update.'
  })
  const updateHasMoreCommits = computed(() => Boolean(updateStatus.value?.hasMoreCommits))
  const updateCompareUrl = computed(() => updateStatus.value?.compareUrl || null)

  const appUpdateNeeded = computed(() => Boolean(appUpdateStatus.value?.updateAvailable))
  const showAppUpdateButton = computed(() => appUpdatePending.value || appUpdateCompleted.value || appUpdateNeeded.value)
  const appUpdateButtonLabel = computed(() => appUpdateCompleted.value ? 'App updated' : 'Update app')
  const appUpdateButtonColor = computed<'primary' | 'success'>(() => appUpdateCompleted.value ? 'success' : 'primary')
  const appUpdateButtonTitle = computed(() => 'Update Hermesum app from origin')

  async function request<T>(path: string, init: RequestInit = {}) {
    const headers = new Headers(init.headers)
    const runtimeToken = runtimeConfig.public.hermesSessionToken
    const token = window.__HERMES_SESSION_TOKEN__ || (typeof runtimeToken === 'string' ? runtimeToken : undefined)
    if (token) headers.set('X-Hermes-Session-Token', token)

    const response = await fetch(path, { ...init, headers })
    if (!response.ok) throw new Error(`Request failed with ${response.status}`)
    return await response.json() as T
  }

  async function loadUpdateStatus() {
    if (updateStatusCheckPending || updatePending.value || appUpdatePending.value) return

    updateStatusCheckPending = true
    lastUpdateStatusCheckAt = Date.now()
    try {
      const [hermesResult, appResult] = await Promise.allSettled([
        request<WebChatUpdateStatusResponse>('/api/web-chat/update'),
        request<WebChatAppUpdateStatusResponse>('/api/web-chat/app-update')
      ])
      updateStatus.value = hermesResult.status === 'fulfilled' ? hermesResult.value : null
      appUpdateStatus.value = appResult.status === 'fulfilled' ? appResult.value : null
    } finally {
      updateStatusCheckPending = false
    }
  }

  function checkUpdateStatusIfDue() {
    if (document.visibilityState !== 'visible') return
    if (Date.now() - lastUpdateStatusCheckAt < UPDATE_STATUS_CHECK_INTERVAL_MS) return

    void loadUpdateStatus()
  }

  async function updateHermes() {
    if (updatePending.value) return
    if (hideUpdateTimer) clearTimeout(hideUpdateTimer)

    updatePending.value = true
    updateCompleted.value = false
    try {
      updateStatus.value = await api.updateHermes()
      updateCompleted.value = true
      launchUpdateFireworks()
      hideUpdateTimer = setTimeout(() => {
        updateCompleted.value = false
      }, 3000)
    } catch (err) {
      toast.add({
        title: 'Update failed',
        description: getHermesErrorMessage(err, 'Could not update Hermes.'),
        color: 'error'
      })
    } finally {
      updatePending.value = false
    }
  }

  async function updateApp() {
    if (appUpdatePending.value) return
    if (hideAppUpdateTimer) clearTimeout(hideAppUpdateTimer)

    appUpdatePending.value = true
    appUpdateCompleted.value = false
    try {
      appUpdateStatus.value = await api.updateApp()
      appUpdateCompleted.value = true
      launchUpdateFireworks()
      hideAppUpdateTimer = setTimeout(() => {
        appUpdateCompleted.value = false
      }, 3000)
    } catch (err) {
      toast.add({
        title: 'App update failed',
        description: getHermesErrorMessage(err, 'Could not update the app.'),
        color: 'error'
      })
    } finally {
      appUpdatePending.value = false
    }
  }

  onMounted(() => {
    void loadUpdateStatus()
    updateStatusTimer = setInterval(checkUpdateStatusIfDue, UPDATE_STATUS_CHECK_INTERVAL_MS)
    document.addEventListener('visibilitychange', checkUpdateStatusIfDue)
  })

  onBeforeUnmount(() => {
    if (updateStatusTimer) clearInterval(updateStatusTimer)
    if (hideUpdateTimer) clearTimeout(hideUpdateTimer)
    if (hideAppUpdateTimer) clearTimeout(hideAppUpdateTimer)
    document.removeEventListener('visibilitychange', checkUpdateStatusIfDue)
  })

  return {
    hermes: {
      visible: showUpdateButton,
      pending: updatePending,
      completed: updateCompleted,
      label: updateButtonLabel,
      color: updateButtonColor,
      title: updateButtonTitle,
      commits: updateCommits,
      hasMoreCommits: updateHasMoreCommits,
      compareUrl: updateCompareUrl,
      revisionSummary: updateRevisionSummary,
      popoverMessage: updatePopoverMessage,
      update: updateHermes
    },
    app: {
      visible: showAppUpdateButton,
      pending: appUpdatePending,
      completed: appUpdateCompleted,
      label: appUpdateButtonLabel,
      color: appUpdateButtonColor,
      title: appUpdateButtonTitle,
      update: updateApp
    }
  }
}
