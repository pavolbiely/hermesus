<script setup lang="ts">
import type { CommandPaletteGroup } from '@nuxt/ui'
import { installNotificationSoundUnlock } from '~/utils/notificationSound'
import { readMessageCountForVisibleSession, syncInitialReadMessageCounts } from '~/utils/chatReadReceipts'
import type { SessionGroup } from '~/utils/sessionGroups'
import type { WebChatAppUpdateStatusResponse, WebChatProfile, WebChatSession, WebChatUpdateStatusResponse, WebChatWorkspace } from '~/types/web-chat'
import { buildSessionGroups } from '~/utils/sessionGroups'

const api = useHermesApi()
const sessionCache = useWebChatSessionCache(api)
const route = useRoute()
const router = useRouter()
const toast = useToast()
const activeChatRuns = useActiveChatRuns()
const context = useChatComposerContext()
const newChatRequest = useNewChatRequest()

const { data, refresh } = await useAsyncData('web-chat-sessions', () => api.listSessions())
const { data: profilesData, pending: profilesPending } = await useAsyncData('web-chat-profiles', () => api.getProfiles())
await context.initialize()

const sessions = computed(() => data.value?.sessions || [])
const groupedSessions = computed<SessionGroup[]>(() => buildSessionGroups({
  sessions: sessions.value,
  workspaces: context.workspaces.value,
  selectedWorkspace: context.selectedWorkspace.value
}))
const searchGroups = computed<CommandPaletteGroup[]>(() => {
  const sessionItems = sessions.value.map(session => ({
    label: sessionTitle(session),
    suffix: session.workspace || undefined,
    icon: session.pinned ? 'i-lucide-pin' : 'i-lucide-message-square',
    active: isActiveSession(session),
    onSelect: () => openSession(session)
  }))

  return sessionItems.length
    ? [{ id: 'chats', label: 'Chats', items: sessionItems }]
    : []
})
const profileOptions = computed(() => (profilesData.value?.profiles || []).map(profile => ({
  label: profile.label,
  value: profile.id,
  profile
})))
const selectedProfile = ref<string | undefined>(profilesData.value?.activeProfile || undefined)
const selectedProfileLabel = computed(() => profileOptions.value.find(option => option.value === selectedProfile.value)?.label)
const profileSwitchPending = ref(false)
const now = ref(new Date())
const readMessageCounts = ref<Record<string, number>>({})
const readMessageCountsLoaded = ref(false)
const readMessageCountsSynced = ref(false)
const renameSession = ref<WebChatSession | null>(null)
const renameTitle = ref('')
const confirmAction = ref<'duplicate' | 'delete' | null>(null)
const confirmSession = ref<WebChatSession | null>(null)
const pendingSessionId = ref<string | null>(null)
const workspaceModalOpen = ref(false)
const editingWorkspace = ref<WebChatWorkspace | null>(null)
const workspaceLabel = ref('')
const workspacePath = ref('')
const workspacePending = ref(false)
const workspaceDirectorySuggestions = ref<string[]>([])
const updateStatus = ref<WebChatUpdateStatusResponse | null>(null)
const updatePending = ref(false)
const updateCompleted = ref(false)
const appUpdateStatus = ref<WebChatAppUpdateStatusResponse | null>(null)
const appUpdatePending = ref(false)
const appUpdateCompleted = ref(false)
let workspaceDirectorySuggestionTimer: ReturnType<typeof setTimeout> | undefined
let hideUpdateTimer: ReturnType<typeof setTimeout> | undefined
let hideAppUpdateTimer: ReturnType<typeof setTimeout> | undefined
let updateStatusTimer: ReturnType<typeof setInterval> | undefined
let updateStatusCheckPending = false
let lastUpdateStatusCheckAt = 0
const READ_MESSAGE_COUNTS_KEY = 'hermes-chat-read-message-counts'
const UPDATE_STATUS_CHECK_INTERVAL_MS = 20 * 60 * 1000
const SESSION_PREFETCH_MESSAGE_LIMIT = 60
let timer: ReturnType<typeof setInterval> | undefined
let unsubscribeRunFinished: (() => void) | undefined
const requestedSessionId = ref<string | null>(null)
const activeSidebarSessionId = computed(() => {
  if (requestedSessionId.value) return requestedSessionId.value
  return typeof route.params.id === 'string' ? route.params.id : undefined
})

const renameModalOpen = computed({
  get: () => Boolean(renameSession.value),
  set: (open) => {
    if (!open) cancelRename()
  }
})

const confirmModalOpen = computed({
  get: () => Boolean(confirmAction.value && confirmSession.value),
  set: (open) => {
    if (!open) cancelConfirmAction()
  }
})

const canRename = computed(() => {
  const session = renameSession.value
  if (!session) return false

  const title = renameTitle.value.trim()
  return Boolean(title) && title !== sessionTitle(session)
})

const canSaveWorkspace = computed(() => Boolean(workspaceLabel.value.trim() && workspacePath.value.trim()))
const updateNeeded = computed(() => Boolean(updateStatus.value?.updateAvailable || updateStatus.value?.runtimeOutOfSync))
const showUpdateButton = computed(() => updatePending.value || updateCompleted.value || updateNeeded.value)
const updateButtonLabel = computed(() => updateCompleted.value ? 'Hermes updated' : 'Update Hermes')
const updateButtonColor = computed(() => updateCompleted.value ? 'success' : 'primary')
const updateButtonTitle = computed(() => {
  if (updateStatus.value?.updateAvailable && updateStatus.value?.runtimeOutOfSync) return 'Update Hermes Agent and sync runtime'
  if (updateStatus.value?.runtimeOutOfSync) return 'Sync Hermes runtime'
  return 'Update Hermes Agent'
})
const appUpdateNeeded = computed(() => Boolean(appUpdateStatus.value?.updateAvailable))
const showAppUpdateButton = computed(() => appUpdatePending.value || appUpdateCompleted.value || appUpdateNeeded.value)
const appUpdateButtonLabel = computed(() => appUpdateCompleted.value ? 'App updated' : 'Update app')
const appUpdateButtonColor = computed(() => appUpdateCompleted.value ? 'success' : 'primary')
const appUpdateButtonTitle = computed(() => 'Update Hermesum app from origin')

const confirmTitle = computed(() => {
  if (!confirmAction.value || !confirmSession.value) return ''

  return confirmAction.value === 'duplicate' ? 'Duplicate chat' : 'Delete chat'
})

const confirmDescription = computed(() => {
  if (!confirmAction.value || !confirmSession.value) return ''

  const title = sessionTitle(confirmSession.value)

  return confirmAction.value === 'duplicate'
    ? `Create a copy of “${title}”?`
    : `Delete “${title}”? This cannot be undone.`
})

function sessionTitle(session: WebChatSession) {
  return session.title || session.preview || 'Untitled chat'
}

async function startNewChat() {
  requestedSessionId.value = null
  newChatRequest.openNewChat(null)
  await router.push('/')
}

async function startWorkspaceChat(workspacePath: string) {
  requestedSessionId.value = null
  newChatRequest.openNewChat(workspacePath)
  await router.push('/')
}

function beginCreateWorkspace() {
  editingWorkspace.value = null
  workspaceLabel.value = ''
  workspacePath.value = ''
  workspaceModalOpen.value = true
}

function beginEditWorkspace(workspace: WebChatWorkspace) {
  editingWorkspace.value = workspace
  workspaceLabel.value = workspace.label
  workspacePath.value = workspace.path
  workspaceModalOpen.value = true
}

function cancelWorkspaceEdit() {
  workspaceModalOpen.value = false
  editingWorkspace.value = null
  workspaceLabel.value = ''
  workspacePath.value = ''
  workspaceDirectorySuggestions.value = []
}

function canSuggestWorkspacePath(path: string) {
  const value = path.trim()
  return value.length >= 2 && (value.startsWith('/') || value.startsWith('~/'))
}

async function loadWorkspaceDirectorySuggestions(prefix: string) {
  if (!canSuggestWorkspacePath(prefix)) {
    workspaceDirectorySuggestions.value = []
    return
  }

  try {
    const response = await api.getWorkspaceDirectories(prefix)
    if (workspacePath.value.trim() === prefix.trim()) {
      workspaceDirectorySuggestions.value = response.suggestions
    }
  } catch {
    workspaceDirectorySuggestions.value = []
  }
}

watch(workspacePath, (path) => {
  if (workspaceDirectorySuggestionTimer) clearTimeout(workspaceDirectorySuggestionTimer)
  workspaceDirectorySuggestionTimer = setTimeout(() => {
    void loadWorkspaceDirectorySuggestions(path)
  }, 150)
})

async function refreshWorkspacesAndSessions() {
  await context.loadWorkspaces(context.selectedWorkspace.value)
  await refresh()
}

async function loadUpdateStatus() {
  if (updateStatusCheckPending || updatePending.value || appUpdatePending.value) return

  updateStatusCheckPending = true
  lastUpdateStatusCheckAt = Date.now()
  try {
    const [hermesResult, appResult] = await Promise.allSettled([
      api.getUpdateStatus(),
      api.getAppUpdateStatus()
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

function handleVisibilityChange() {
  checkUpdateStatusIfDue()
}

async function updateHermes() {
  if (updatePending.value) return
  if (hideUpdateTimer) clearTimeout(hideUpdateTimer)

  updatePending.value = true
  updateCompleted.value = false
  try {
    updateStatus.value = await api.updateHermes()
    updateCompleted.value = true
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

async function saveWorkspace() {
  if (!canSaveWorkspace.value) return

  workspacePending.value = true
  try {
    const payload = { label: workspaceLabel.value.trim(), path: workspacePath.value.trim() }
    const response = editingWorkspace.value
      ? await api.updateWorkspace(editingWorkspace.value.id, payload)
      : await api.createWorkspace(payload)
    context.selectWorkspace(response.workspace.path)
    await refreshWorkspacesAndSessions()
    cancelWorkspaceEdit()
  } catch (err) {
    toast.add({
      title: editingWorkspace.value ? 'Failed to update workspace' : 'Failed to add workspace',
      description: getHermesErrorMessage(err, 'Could not save workspace.'),
      color: 'error'
    })
  } finally {
    workspacePending.value = false
  }
}

async function deleteWorkspace() {
  const workspace = editingWorkspace.value
  if (!workspace) return

  workspacePending.value = true
  try {
    await api.deleteWorkspace(workspace.id)
    if (context.selectedWorkspace.value === workspace.path) context.selectWorkspace(null)
    await refreshWorkspacesAndSessions()
    cancelWorkspaceEdit()
  } catch (err) {
    toast.add({
      title: 'Failed to delete workspace',
      description: getHermesErrorMessage(err, 'Could not delete workspace.'),
      color: 'error'
    })
  } finally {
    workspacePending.value = false
  }
}

function activeProfileId() {
  return profilesData.value?.profiles.find(profile => profile.active)?.id
    || profilesData.value?.activeProfile
    || undefined
}

async function reloadWhenProfileReady(profile: string) {
  if (!import.meta.client) return

  const deadline = Date.now() + 12_000
  while (Date.now() < deadline) {
    await new Promise(resolve => window.setTimeout(resolve, 600))

    try {
      const response = await api.getProfiles()
      profilesData.value = response
      selectedProfile.value = response.activeProfile
      if (response.activeProfile === profile || response.profiles.some(item => item.id === profile && item.active)) {
        window.location.reload()
        return
      }
    } catch {
      // Backend may be between process exit and restart.
    }
  }

  window.location.reload()
}

async function selectProfile(profileId: string | WebChatProfile | null) {
  const requested = typeof profileId === 'string' ? profileId : profileId?.id || null
  const active = activeProfileId()
  if (!requested || requested === active || profileSwitchPending.value) {
    selectedProfile.value = active
    return
  }

  selectedProfile.value = requested
  profileSwitchPending.value = true
  let keepPending = false
  try {
    const response = await api.switchProfile(requested)
    profilesData.value = response
    selectedProfile.value = response.activeProfile
    toast.add({
      title: response.restarting ? 'Switching profile…' : 'Profile switched',
      description: response.restarting
        ? `Hermes backend is restarting with profile “${response.activeProfile}”.`
        : `Active profile: ${response.activeProfile}.`,
      color: 'neutral'
    })

    if (response.restarting && import.meta.client) {
      keepPending = true
      void reloadWhenProfileReady(response.activeProfile)
    }
  } catch (err) {
    selectedProfile.value = active
    toast.add({
      title: 'Failed to switch profile',
      description: getHermesErrorMessage(err, 'Could not switch Hermes profile.'),
      color: 'error'
    })
  } finally {
    if (!keepPending) profileSwitchPending.value = false
  }
}

watch(profilesData, () => {
  selectedProfile.value = activeProfileId()
}, { immediate: true })

function isActiveSession(session: WebChatSession) {
  return route.params.id === session.id
}

function loadReadMessageCounts() {
  if (!import.meta.client || readMessageCountsLoaded.value) return

  try {
    const stored = localStorage.getItem(READ_MESSAGE_COUNTS_KEY)
    const parsed = stored ? JSON.parse(stored) : {}
    readMessageCounts.value = typeof parsed === 'object' && parsed && !Array.isArray(parsed)
      ? Object.fromEntries(
          Object.entries(parsed)
            .filter(([, value]) => typeof value === 'number' && Number.isFinite(value))
        ) as Record<string, number>
      : {}
  } catch {
    readMessageCounts.value = {}
  } finally {
    readMessageCountsLoaded.value = true
  }
}

function saveReadMessageCounts() {
  if (!import.meta.client || !readMessageCountsLoaded.value) return
  localStorage.setItem(READ_MESSAGE_COUNTS_KEY, JSON.stringify(readMessageCounts.value))
}

function markSessionRead(sessionId: string, messageCount: number) {
  if (!readMessageCountsLoaded.value) return
  const session = sessions.value.find(session => session.id === sessionId)
  const currentCount = readMessageCountForVisibleSession(session, messageCount)
  if (readMessageCounts.value[sessionId] === currentCount) return
  readMessageCounts.value = { ...readMessageCounts.value, [sessionId]: currentCount }
  saveReadMessageCounts()
}

function initialReadMessageCount(session: Pick<WebChatSession, 'id' | 'messageCount'>) {
  if (!readMessageCountsSynced.value) return session.messageCount || 0
  return session.id === activeSidebarSessionId.value ? session.messageCount || 0 : 0
}

function syncReadMessageCounts() {
  if (!readMessageCountsLoaded.value) return

  const next = syncInitialReadMessageCounts(sessions.value, readMessageCounts.value, initialReadMessageCount)
  readMessageCountsSynced.value = true
  if (next === readMessageCounts.value) return

  readMessageCounts.value = next
  saveReadMessageCounts()
}

function isSessionRunning(session: WebChatSession) {
  return activeChatRuns.isRunning(session.id)
}

function hasLocalUnread(session: WebChatSession) {
  return activeChatRuns.hasLocalUnread(session.id)
}

function beginRename(session: WebChatSession) {
  renameSession.value = session
  renameTitle.value = sessionTitle(session)
}

function cancelRename() {
  renameSession.value = null
  renameTitle.value = ''
}

async function saveRename() {
  const session = renameSession.value
  if (!session) return

  const title = renameTitle.value.trim()
  if (!title || title === sessionTitle(session)) {
    cancelRename()
    return
  }

  pendingSessionId.value = session.id
  try {
    await api.renameSession(session.id, title)
    await refresh()
    cancelRename()
  } catch (err) {
    toast.add({
      title: 'Failed to rename chat',
      description: err instanceof Error ? err.message : String(err),
      color: 'error'
    })
  } finally {
    pendingSessionId.value = null
  }
}

function beginConfirmAction(action: 'duplicate' | 'delete', session: WebChatSession) {
  confirmAction.value = action
  confirmSession.value = session
}

function cancelConfirmAction() {
  confirmAction.value = null
  confirmSession.value = null
}

async function confirmSessionAction() {
  const action = confirmAction.value
  const session = confirmSession.value
  if (!action || !session) return

  if (action === 'duplicate') {
    await duplicateSession(session)
  } else {
    await deleteSession(session)
  }
}

async function duplicateSession(session: WebChatSession) {
  pendingSessionId.value = session.id
  try {
    const duplicated = await api.duplicateSession(session.id)
    sessionCache.set(duplicated)
    await refresh()
    cancelConfirmAction()
    await router.push(`/chat/${duplicated.session.id}`)
  } catch (err) {
    toast.add({
      title: 'Failed to duplicate chat',
      description: err instanceof Error ? err.message : String(err),
      color: 'error'
    })
  } finally {
    pendingSessionId.value = null
  }
}

async function toggleSessionPinned(session: WebChatSession) {
  pendingSessionId.value = session.id
  try {
    await api.setSessionPinned(session.id, !session.pinned)
    await refresh()
  } catch (err) {
    toast.add({
      title: session.pinned ? 'Failed to unpin chat' : 'Failed to pin chat',
      description: err instanceof Error ? err.message : String(err),
      color: 'error'
    })
  } finally {
    pendingSessionId.value = null
  }
}

async function deleteSession(session: WebChatSession) {
  pendingSessionId.value = session.id
  try {
    await api.deleteSession(session.id)
    sessionCache.remove(session.id)
    activeChatRuns.markFinished(session.id)
    await refresh()
    cancelConfirmAction()
    if (isActiveSession(session)) await router.push('/')
  } catch (err) {
    toast.add({
      title: 'Failed to delete chat',
      description: err instanceof Error ? err.message : String(err),
      color: 'error'
    })
  } finally {
    pendingSessionId.value = null
  }
}

function prefetchSession(session: WebChatSession) {
  sessionCache.prefetch(session.id, { messageLimit: SESSION_PREFETCH_MESSAGE_LIMIT })
}

function openSession(session: WebChatSession) {
  requestedSessionId.value = session.id
  void router.push(`/chat/${session.id}`).catch(() => {
    requestedSessionId.value = null
  })
}

watch(
  () => route.params.id,
  (id) => {
    if (requestedSessionId.value === id) requestedSessionId.value = null
  }
)

watch(
  () => [route.params.id, sessions.value.map(session => `${session.id}:${session.messageCount}`).join('|')],
  () => syncReadMessageCounts()
)

onMounted(() => {
  installNotificationSoundUnlock()
  loadReadMessageCounts()
  syncReadMessageCounts()
  void loadUpdateStatus()
  updateStatusTimer = setInterval(checkUpdateStatusIfDue, UPDATE_STATUS_CHECK_INTERVAL_MS)
  document.addEventListener('visibilitychange', handleVisibilityChange)
  timer = setInterval(() => {
    now.value = new Date()
  }, 15_000)
  unsubscribeRunFinished = activeChatRuns.onFinished(() => refresh())
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  if (updateStatusTimer) clearInterval(updateStatusTimer)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  if (workspaceDirectorySuggestionTimer) clearTimeout(workspaceDirectorySuggestionTimer)
  if (hideUpdateTimer) clearTimeout(hideUpdateTimer)
  if (hideAppUpdateTimer) clearTimeout(hideAppUpdateTimer)
  unsubscribeRunFinished?.()
})

provide('refreshSessions', refresh)
provide('markSessionRead', markSessionRead)
provide('requestedSessionId', readonly(requestedSessionId))
provide('hermesUpdateControl', {
  visible: showUpdateButton,
  pending: updatePending,
  completed: updateCompleted,
  label: updateButtonLabel,
  color: updateButtonColor,
  title: updateButtonTitle,
  update: updateHermes
})
provide('appUpdateControl', {
  visible: showAppUpdateButton,
  pending: appUpdatePending,
  completed: appUpdateCompleted,
  label: appUpdateButtonLabel,
  color: appUpdateButtonColor,
  title: appUpdateButtonTitle,
  update: updateApp
})
</script>

<template>
  <UDashboardGroup :persistent="false">
    <UDashboardSidebar collapsible :default-size="22" class="bg-elevated/25">
      <template #header>
        <NuxtLink to="/" class="flex h-8 w-full shrink-0 items-center px-0.5">
          <img
            src="/logo.svg"
            alt="Hermes Agent"
            class="h-auto w-full object-contain"
          >
        </NuxtLink>
      </template>

      <template #default>
        <div class="-mt-2 space-y-2 px-0.5 pb-3">
          <div class="grid grid-cols-2 gap-1.5">
            <UButton
              block
              color="neutral"
              variant="soft"
              size="xs"
              icon="i-lucide-square-pen"
              label="Chat"
              @click="startNewChat"
            />
            <UButton
              block
              color="neutral"
              variant="soft"
              size="xs"
              icon="i-lucide-folder-plus"
              label="Workspace"
              @click="beginCreateWorkspace"
            />
          </div>

          <UDashboardSearchButton
            label="Search chats"
            variant="soft"
            size="xs"
            class="w-full justify-start"
          />
        </div>

        <SidebarSessionGroups
          :groups="groupedSessions"
          :active-session-id="activeSidebarSessionId"
          :pending-session-id="pendingSessionId"
          :now="now"
          :read-message-counts="readMessageCounts"
          :read-message-counts-loaded="readMessageCountsLoaded"
          :is-session-running="isSessionRunning"
          :has-local-unread="hasLocalUnread"
          @edit-workspace="beginEditWorkspace"
          @start-workspace-chat="startWorkspaceChat"
          @open-session="openSession"
          @prefetch-session="prefetchSession"
          @rename-session="beginRename"
          @toggle-session-pinned="toggleSessionPinned"
          @confirm-session-action="beginConfirmAction"
        />
      </template>

      <template #footer>
        <div class="w-full pb-1">
          <USelectMenu
            :model-value="selectedProfile"
            :items="profileOptions"
            value-key="value"
            label-key="label"
            size="xs"
            class="block w-full max-w-none"
            :ui="{
              base: 'w-full max-w-none !justify-start text-left',
              value: 'flex-1 text-left',
              placeholder: 'flex-1 text-left',
              trailing: 'ms-auto'
            }"
            :loading="profilesPending || profileSwitchPending"
            :disabled="profilesPending || profileSwitchPending || !profileOptions.length"
            placeholder="Hermes profile"
            @update:model-value="selectProfile"
          >
            <template #default>
              <span class="min-w-0 flex-1 truncate text-left">
                {{ selectedProfileLabel || 'Hermes profile' }}
              </span>
            </template>
            <template #leading>
              <UIcon
                :name="profileSwitchPending ? 'i-lucide-loader-circle' : 'i-lucide-user-round'"
                class="size-3.5"
                :class="profileSwitchPending ? 'animate-spin' : undefined"
              />
            </template>
          </USelectMenu>
        </div>
      </template>
    </UDashboardSidebar>

    <UDashboardSearch
      placeholder="Search chats..."
      :groups="searchGroups"
      :fuse="{ resultLimit: 20 }"
      :color-mode="false"
    />

    <slot />

    <WorkspaceModal
      v-model:open="workspaceModalOpen"
      v-model:label="workspaceLabel"
      v-model:path="workspacePath"
      :editing-workspace="editingWorkspace"
      :suggestions="workspaceDirectorySuggestions"
      :pending="workspacePending"
      :can-save="canSaveWorkspace"
      @save="saveWorkspace"
      @cancel="cancelWorkspaceEdit"
      @delete="deleteWorkspace"
    />

    <ChatRenameModal
      v-model:open="renameModalOpen"
      v-model:title="renameTitle"
      :pending="pendingSessionId === renameSession?.id"
      :can-rename="canRename"
      @save="saveRename"
      @cancel="cancelRename"
    />

    <ChatConfirmActionModal
      v-model:open="confirmModalOpen"
      :action="confirmAction"
      :title="confirmTitle"
      :description="confirmDescription"
      :pending="pendingSessionId === confirmSession?.id"
      @confirm="confirmSessionAction"
      @cancel="cancelConfirmAction"
    />
  </UDashboardGroup>
</template>
