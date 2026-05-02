<script setup lang="ts">
import type { CommandPaletteGroup } from '@nuxt/ui'
import { installNotificationSoundUnlock } from '~/utils/notificationSound'
import { readMessageCountForVisibleSession, syncInitialReadMessageCounts } from '~/utils/chatReadReceipts'
import type { SessionGroup } from '~/utils/sessionGroups'
import type { WebChatMessage, WebChatProfile, WebChatSession, WebChatWorkspace } from '~/types/web-chat'
import { buildSessionGroups } from '~/utils/sessionGroups'

type ConfirmSessionAction = 'duplicate' | 'archive' | 'delete'

const api = useHermesApi()
const sessionCache = useWebChatSessionCache(api)
const route = useRoute()
const router = useRouter()
const toast = useToast()
const activeChatRuns = useActiveChatRuns()
const context = useChatComposerContext()
const newChatRequest = useNewChatRequest()

const dataRefreshKey = 'web-chat-sessions'
const { data, refresh } = await useAsyncData(dataRefreshKey, () => api.listSessions({ includeArchived: true }))
const { data: profilesData, pending: profilesPending } = await useAsyncData('web-chat-profiles', () => api.getProfiles())
await context.initialize()

const sessions = computed(() => data.value?.sessions || [])
const groupedSessions = computed<SessionGroup[]>(() => buildSessionGroups({
  sessions: sessions.value,
  workspaces: context.workspaces.value,
  selectedWorkspace: context.selectedWorkspace.value
}))
const searchTerm = ref('')
const searchMessageTextBySessionId = ref<Record<string, string>>({})
const searchIndexedSessionIds = ref(new Set<string>())
const searchGroups = computed<CommandPaletteGroup[]>(() => {
  const query = normalizeSearchText(searchTerm.value)
  const sessionItems = sessions.value
    .filter(session => !query || sessionSearchText(session).includes(query))
    .map(session => ({
      label: sessionTitle(session),
      suffix: workspaceDisplayLabel(session.workspace) || undefined,
      icon: session.pinned ? 'i-lucide-pin' : 'i-lucide-message-square',
      active: isActiveSession(session),
      onSelect: () => openSession(session)
    }))

  return sessionItems.length
    ? [{ id: 'chats', label: 'Chats', ignoreFilter: Boolean(query), items: sessionItems }]
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
const confirmAction = ref<ConfirmSessionAction | null>(null)
const confirmSession = ref<WebChatSession | null>(null)
const pendingSessionId = ref<string | null>(null)
const workspaceModalOpen = ref(false)
const settingsModalOpen = ref(false)
const editingWorkspace = ref<WebChatWorkspace | null>(null)
const workspaceLabel = ref('')
const workspacePath = ref('')
const workspacePending = ref(false)
const workspaceDirectorySuggestions = ref<string[]>([])
let workspaceDirectorySuggestionTimer: ReturnType<typeof setTimeout> | undefined
let searchIndexTimer: ReturnType<typeof setTimeout> | undefined
const READ_MESSAGE_COUNTS_KEY = 'hermes-chat-read-message-counts'
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
const confirmTitle = computed(() => {
  if (!confirmAction.value || !confirmSession.value) return ''

  if (confirmAction.value === 'duplicate') return 'Duplicate chat'
  if (confirmAction.value === 'archive') return 'Archive chat'
  return 'Delete chat'
})

const confirmDescription = computed(() => {
  if (!confirmAction.value || !confirmSession.value) return ''

  const title = sessionTitle(confirmSession.value)

  if (confirmAction.value === 'duplicate') return `Create a copy of “${title}”?`
  if (confirmAction.value === 'archive') return `Archive “${title}”? It will move to the Archived section.`
  return `Permanently delete “${title}”? This cannot be undone.`
})

function sessionTitle(session: WebChatSession) {
  return session.title || session.preview || 'Untitled chat'
}

function syncActiveRunSessionTitles() {
  for (const session of sessions.value) {
    activeChatRuns.setSessionTitle(session.id, sessionTitle(session))
  }
}

function workspaceDisplayLabel(path: string | null) {
  if (!path) return null
  return context.workspaces.value.find(workspace => workspace.path === path)?.label || path
}

function normalizeSearchText(value: string | null | undefined) {
  return (value || '').toLowerCase()
}

function sessionSearchText(session: WebChatSession) {
  return normalizeSearchText([
    sessionTitle(session),
    session.preview,
    workspaceDisplayLabel(session.workspace),
    session.workspace,
    searchMessageTextBySessionId.value[session.id]
  ].filter(Boolean).join(' '))
}

function messageSearchText(message: WebChatMessage) {
  return message.parts
    .map(part => part.text || part.description || part.title || '')
    .filter(Boolean)
    .join(' ')
}

function sessionMessagesSearchText(messages: WebChatMessage[]) {
  return messages.map(messageSearchText).filter(Boolean).join(' ')
}

async function indexSessionsForSearch() {
  const query = normalizeSearchText(searchTerm.value.trim())
  if (query.length < 2) return

  const indexedIds = searchIndexedSessionIds.value
  const sessionsToIndex = sessions.value.filter(session => !indexedIds.has(session.id))
  if (!sessionsToIndex.length) return

  await Promise.allSettled(sessionsToIndex.map(async (session) => {
    const detail = await api.getSession(session.id, { includeWorkspaceChanges: false })
    searchMessageTextBySessionId.value = {
      ...searchMessageTextBySessionId.value,
      [session.id]: sessionMessagesSearchText(detail.messages)
    }
    searchIndexedSessionIds.value = new Set([...searchIndexedSessionIds.value, session.id])
  }))
}

function startWorkspaceChat(workspacePath: string) {
  requestedSessionId.value = null
  context.selectWorkspace(workspacePath)
  newChatRequest.openNewChat(workspacePath)
  void router.push('/')
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

watch(searchTerm, () => {
  if (searchIndexTimer) clearTimeout(searchIndexTimer)
  searchIndexTimer = setTimeout(() => {
    void indexSessionsForSearch()
  }, 200)
})

async function refreshWorkspacesAndSessions() {
  await context.loadWorkspaces(context.selectedWorkspace.value)
  await refresh()
}

function applyWorkspaceOrder(workspaces: WebChatWorkspace[], workspaceIds: string[]) {
  const workspacesById = new Map(workspaces.map(workspace => [workspace.id, workspace]))
  const requestedIds = new Set(workspaceIds)
  return [
    ...workspaceIds.map(id => workspacesById.get(id)).filter((workspace): workspace is WebChatWorkspace => Boolean(workspace)),
    ...workspaces.filter(workspace => !requestedIds.has(workspace.id))
  ]
}

async function reorderWorkspaces(workspaceIds: string[]) {
  const previousWorkspaces = context.workspaces.value
  context.workspaces.value = applyWorkspaceOrder(previousWorkspaces, workspaceIds)

  try {
    const response = await api.reorderWorkspaces({ workspaceIds })
    context.workspaces.value = response.workspaces
  } catch (err) {
    context.workspaces.value = previousWorkspaces
    toast.add({
      title: 'Failed to reorder workspaces',
      description: getHermesErrorMessage(err, 'Could not save workspace order.'),
      color: 'error'
    })
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

function beginConfirmAction(action: ConfirmSessionAction, session: WebChatSession) {
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
  } else if (action === 'archive') {
    await archiveSession(session)
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

async function setSessionArchived(session: WebChatSession, archived: boolean) {
  pendingSessionId.value = session.id
  try {
    const response = await api.setSessionArchived(session.id, archived)
    sessionCache.set(response)
    await refresh()
    if (archived && isActiveSession(session)) await router.push('/')
  } catch (err) {
    const message = getHermesErrorMessage(err, archived ? 'Could not archive chat.' : 'Could not restore chat.')
    if (!archived && message.includes('Choose another workspace')) {
      await router.push(`/chat/${session.id}`)
      toast.add({
        title: 'Choose a workspace to restore this chat',
        description: 'The original workspace no longer exists.',
        color: 'warning'
      })
      return
    }
    toast.add({
      title: archived ? 'Failed to archive chat' : 'Failed to restore chat',
      description: message,
      color: 'error'
    })
  } finally {
    pendingSessionId.value = null
  }
}

async function archiveSession(session: WebChatSession) {
  await setSessionArchived(session, true)
  cancelConfirmAction()
}

async function restoreSession(session: WebChatSession) {
  await setSessionArchived(session, false)
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

watch(sessions, syncActiveRunSessionTitles, { immediate: true })

onMounted(() => {
  installNotificationSoundUnlock()
  loadReadMessageCounts()
  syncReadMessageCounts()
  timer = setInterval(() => {
    now.value = new Date()
  }, 15_000)
  unsubscribeRunFinished = activeChatRuns.onFinished(() => refresh())
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  if (workspaceDirectorySuggestionTimer) clearTimeout(workspaceDirectorySuggestionTimer)
  if (searchIndexTimer) clearTimeout(searchIndexTimer)
  unsubscribeRunFinished?.()
})

provide('refreshSessions', refresh)
provide('markSessionRead', markSessionRead)
provide('requestedSessionId', readonly(requestedSessionId))
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
        <div class="-mt-2 px-0.5 pb-1">
          <UDashboardSearchButton
            label="Search chats"
            variant="soft"
            size="xs"
            class="w-full justify-start"
          />
        </div>

        <div class="flex h-6 items-center justify-between px-2 text-sm font-medium text-muted">
          <span>Workspaces</span>
          <UTooltip text="New workspace">
            <UButton
              aria-label="New workspace"
              icon="i-lucide-folder-plus"
              color="neutral"
              variant="ghost"
              size="xs"
              square
              class="mr-1 size-5"
              :ui="{ leadingIcon: 'size-3.5' }"
              @click="beginCreateWorkspace"
            />
          </UTooltip>
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
          @reorder-workspaces="reorderWorkspaces"
          @open-session="openSession"
          @prefetch-session="prefetchSession"
          @rename-session="beginRename"
          @toggle-session-pinned="toggleSessionPinned"
          @restore-session="restoreSession"
          @confirm-session-action="beginConfirmAction"
        />
      </template>

      <template #footer>
        <div class="flex w-full items-center gap-1 pb-1">
          <USelectMenu
            :model-value="selectedProfile"
            :items="profileOptions"
            value-key="value"
            label-key="label"
            size="xs"
            class="block min-w-0 flex-1 max-w-none"
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
                :name="profileSwitchPending ? 'i-lucide-cpu' : 'i-lucide-user-round'"
                class="size-3.5"
                :class="profileSwitchPending ? 'animate-spin' : undefined"
              />
            </template>
          </USelectMenu>

          <UTooltip text="Settings">
            <UButton
              aria-label="Settings"
              icon="i-lucide-settings"
              color="neutral"
              variant="ghost"
              size="xs"
              square
              class="shrink-0"
              @click="settingsModalOpen = true"
            />
          </UTooltip>
        </div>
      </template>
    </UDashboardSidebar>

    <UDashboardSearch
      v-model:search-term="searchTerm"
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

    <SettingsModal v-model:open="settingsModalOpen" />

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
