<script setup lang="ts">
import type { CommandPaletteGroup } from '@nuxt/ui'
import { installNotificationSoundUnlock } from '~/utils/notificationSound'
import { readMessageCountForVisibleSession, syncInitialReadMessageCounts } from '~/utils/chatReadReceipts'
import type { SessionGroup } from '~/utils/sessionGroups'
import type { AppWorkspace, ChatSessionSummary } from '~/types/chat'
import { acpSidebarSessions } from '~/utils/acpSidebarSessions'
import { buildSessionGroups } from '~/utils/sessionGroups'

type ConfirmSessionAction = 'duplicate' | 'archive' | 'delete'

const api = useAppWorkspacesApi()
const acpApi = useAcpApi()
const route = useRoute()
const router = useRouter()
const toast = useToast()
const context = useChatComposerContext()
const newChatRequest = useNewChatRequest()
const readAloud = useAcpMessageReadAloud()

const dataRefreshKey = 'acp-sidebar-sessions'
const { data, refresh } = await useAsyncData(dataRefreshKey, () => acpApi.listSessions())
await context.initialize()

const sessions = computed(() => acpSidebarSessions(data.value))
const groupedSessions = computed<SessionGroup[]>(() => buildSessionGroups({
  sessions: sessions.value,
  workspaces: context.workspaces.value,
  selectedWorkspace: context.selectedWorkspace.value
}))
const searchTerm = ref('')
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
const now = ref(new Date())
const readMessageCounts = ref<Record<string, number>>({})
const readMessageCountsLoaded = ref(false)
const readMessageCountsSynced = ref(false)
const renameSession = ref<ChatSessionSummary | null>(null)
const renameTitle = ref('')
const confirmAction = ref<ConfirmSessionAction | null>(null)
const confirmSession = ref<ChatSessionSummary | null>(null)
const pendingSessionId = ref<string | null>(null)
const workspaceModalOpen = ref(false)
const settingsModalOpen = ref(false)
const editingWorkspace = ref<AppWorkspace | null>(null)
const workspaceLabel = ref('')
const workspacePath = ref('')
const workspacePending = ref(false)
const workspaceDirectorySuggestions = ref<string[]>([])
let workspaceDirectorySuggestionTimer: ReturnType<typeof setTimeout> | undefined
const READ_MESSAGE_COUNTS_KEY = 'hermes-chat-read-message-counts'
let timer: ReturnType<typeof setInterval> | undefined
const requestedSessionId = ref<string | null>(null)
const activeSidebarSessionId = computed(() => {
  if (requestedSessionId.value) return requestedSessionId.value
  return typeof route.params.id === 'string' ? route.params.id : undefined
})
const readAloudSessionId = computed(() => readAloud.generatingSessionId.value || readAloud.speakingSessionId.value)
const readAloudStatus = computed(() => readAloud.status.value)

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

function sessionTitle(session: ChatSessionSummary) {
  return session.title || session.preview || 'Untitled chat'
}

function workspaceDisplayLabel(path: string | null) {
  if (!path) return null
  return context.workspaces.value.find(workspace => workspace.path === path)?.label || path
}

function normalizeSearchText(value: string | null | undefined) {
  return (value || '').toLowerCase()
}

function sessionSearchText(session: ChatSessionSummary) {
  return normalizeSearchText([
    sessionTitle(session),
    session.preview,
    workspaceDisplayLabel(session.workspace),
    session.workspace
  ].filter(Boolean).join(' '))
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

function beginEditWorkspace(workspace: AppWorkspace) {
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

function applyWorkspaceOrder(workspaces: AppWorkspace[], workspaceIds: string[]) {
  const workspacesById = new Map(workspaces.map(workspace => [workspace.id, workspace]))
  const requestedIds = new Set(workspaceIds)
  return [
    ...workspaceIds.map(id => workspacesById.get(id)).filter((workspace): workspace is AppWorkspace => Boolean(workspace)),
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


function isActiveSession(session: ChatSessionSummary) {
  return route.path === `/acp/${session.id}`
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

function initialReadMessageCount(session: Pick<ChatSessionSummary, 'id' | 'messageCount'>) {
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

function isSessionRunning(_session: ChatSessionSummary) {
  return false
}

function hasLocalUnread(_session: ChatSessionSummary) {
  return false
}

function beginRename(session: ChatSessionSummary) {
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
    await acpApi.updateSessionMetadata(session.id, { title })
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

function beginConfirmAction(action: ConfirmSessionAction, session: ChatSessionSummary) {
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

async function duplicateSession(session: ChatSessionSummary) {
  pendingSessionId.value = session.id
  try {
    const duplicated = await acpApi.forkSession(session.id)
    await refresh()
    cancelConfirmAction()
    await router.push(`/acp/${duplicated.sessionId}`)
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

async function toggleSessionPinned(session: ChatSessionSummary) {
  pendingSessionId.value = session.id
  try {
    await acpApi.updateSessionMetadata(session.id, { pinned: !session.pinned })
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

async function moveSessionToWorkspace(session: ChatSessionSummary, workspace: AppWorkspace) {
  if (session.workspace === workspace.path) return

  pendingSessionId.value = session.id
  try {
    await acpApi.updateSessionMetadata(session.id, { workspace: workspace.path })
    await refresh()
    toast.add({
      title: 'Chat moved',
      description: `Moved to ${workspace.label}.`,
      color: 'success'
    })
  } catch (err) {
    toast.add({
      title: 'Failed to move chat',
      description: err instanceof Error ? err.message : String(err),
      color: 'error'
    })
  } finally {
    pendingSessionId.value = null
  }
}

async function setSessionArchived(session: ChatSessionSummary, archived: boolean) {
  pendingSessionId.value = session.id
  try {
    await acpApi.updateSessionMetadata(session.id, { archived })
    await refresh()
    if (archived && isActiveSession(session)) await router.push('/')
  } catch (err) {
    const message = getHermesErrorMessage(err, archived ? 'Could not archive chat.' : 'Could not restore chat.')
    toast.add({
      title: archived ? 'Failed to archive chat' : 'Failed to restore chat',
      description: message,
      color: 'error'
    })
  } finally {
    pendingSessionId.value = null
  }
}

async function archiveSession(session: ChatSessionSummary) {
  await setSessionArchived(session, true)
  cancelConfirmAction()
}

async function restoreSession(session: ChatSessionSummary) {
  await setSessionArchived(session, false)
}

async function deleteSession(session: ChatSessionSummary) {
  pendingSessionId.value = session.id
  try {
    await acpApi.closeSession(session.id)
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

function prefetchSession(_session: ChatSessionSummary) {
}

function stopReadAloud(sessionId: string) {
  readAloud.stopSession(sessionId)
}

function openSession(session: ChatSessionSummary) {
  requestedSessionId.value = session.id
  void router.push(`/acp/${session.id}`).catch(() => {
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
  timer = setInterval(() => {
    now.value = new Date()
  }, 15_000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  if (workspaceDirectorySuggestionTimer) clearTimeout(workspaceDirectorySuggestionTimer)
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
          :workspaces="context.workspaces.value"
          :active-session-id="activeSidebarSessionId"
          :pending-session-id="pendingSessionId"
          :now="now"
          :read-message-counts="readMessageCounts"
          :read-message-counts-loaded="readMessageCountsLoaded"
          :is-session-running="isSessionRunning"
          :has-local-unread="hasLocalUnread"
          :read-aloud-session-id="readAloudSessionId"
          :read-aloud-status="readAloudStatus"
          @edit-workspace="beginEditWorkspace"
          @start-workspace-chat="startWorkspaceChat"
          @reorder-workspaces="reorderWorkspaces"
          @open-session="openSession"
          @prefetch-session="prefetchSession"
          @rename-session="beginRename"
          @move-session-to-workspace="moveSessionToWorkspace"
          @toggle-session-pinned="toggleSessionPinned"
          @restore-session="restoreSession"
          @confirm-session-action="beginConfirmAction"
          @stop-read-aloud="stopReadAloud"
        />
      </template>

      <template #footer>
        <div class="flex w-full items-center justify-end pb-1">
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
