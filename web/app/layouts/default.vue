<script setup lang="ts">
import { installNotificationSoundUnlock } from '~/utils/notificationSound'
import { readMessageCountForVisibleSession, syncInitialReadMessageCounts } from '~/utils/chatReadReceipts'
import type { SessionGroup } from '~/utils/sessionGroups'
import type { WebChatProfile, WebChatSession, WebChatWorkspace } from '~/types/web-chat'
import { buildSessionGroups } from '~/utils/sessionGroups'

const api = useHermesApi()
const route = useRoute()
const router = useRouter()
const toast = useToast()
const activeChatRuns = useActiveChatRuns()
const context = useChatComposerContext()

const { data, refresh } = await useAsyncData('web-chat-sessions', () => api.listSessions())
const { data: profilesData, pending: profilesPending } = await useAsyncData('web-chat-profiles', () => api.getProfiles())
await context.initialize()

const sessions = computed(() => data.value?.sessions || [])
const groupedSessions = computed<SessionGroup[]>(() => buildSessionGroups({
  sessions: sessions.value,
  workspaces: context.workspaces.value,
  selectedWorkspace: context.selectedWorkspace.value
}))
const profileOptions = computed(() => (profilesData.value?.profiles || []).map(profile => ({
  label: profile.label,
  value: profile.id,
  profile
})))
const selectedProfile = ref<string | undefined>(profilesData.value?.activeProfile || undefined)
const profileSwitchPending = ref(false)
const now = ref(new Date())
const readMessageCounts = ref<Record<string, number>>({})
const readMessageCountsLoaded = ref(false)
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
let workspaceDirectorySuggestionTimer: ReturnType<typeof setTimeout> | undefined
const READ_MESSAGE_COUNTS_KEY = 'hermes-chat-read-message-counts'
let timer: ReturnType<typeof setInterval> | undefined
let unsubscribeRunFinished: (() => void) | undefined

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
  context.selectWorkspace(null)
  await router.push('/')
}

async function startWorkspaceChat(workspacePath: string) {
  context.selectWorkspace(workspacePath)
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

function syncReadMessageCounts() {
  if (!readMessageCountsLoaded.value) return

  const next = syncInitialReadMessageCounts(sessions.value, readMessageCounts.value)
  if (next === readMessageCounts.value) return

  readMessageCounts.value = next
  saveReadMessageCounts()
}

function isSessionRunning(session: WebChatSession) {
  return activeChatRuns.isRunning(session.id)
}

function hasPromptUnread(session: WebChatSession) {
  return activeChatRuns.hasPromptUnread(session.id)
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

async function deleteSession(session: WebChatSession) {
  pendingSessionId.value = session.id
  try {
    await api.deleteSession(session.id)
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

function openSession(session: WebChatSession) {
  void router.push(`/chat/${session.id}`)
}

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
  unsubscribeRunFinished = activeChatRuns.onFinished(() => refresh())
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  if (workspaceDirectorySuggestionTimer) clearTimeout(workspaceDirectorySuggestionTimer)
  unsubscribeRunFinished?.()
})

provide('refreshSessions', refresh)
provide('markSessionRead', markSessionRead)
</script>

<template>
  <UDashboardGroup>
    <UDashboardSidebar collapsible :default-size="20">
      <template #header>
        <NuxtLink to="/" class="flex h-8 w-full shrink-0 items-center px-2">
          <img
            src="/logo.svg"
            alt="Hermes Agent"
            class="h-auto w-full object-contain"
          >
        </NuxtLink>
      </template>

      <template #default>
        <div class="-mt-2 space-y-2 px-2 pb-3">
          <USelectMenu
            :model-value="selectedProfile"
            :items="profileOptions"
            value-key="value"
            label-key="label"
            size="sm"
            class="w-full"
            :loading="profilesPending || profileSwitchPending"
            :disabled="profilesPending || profileSwitchPending || !profileOptions.length"
            placeholder="Hermes profile"
            @update:model-value="selectProfile"
          >
            <template #leading>
              <UIcon
                :name="profileSwitchPending ? 'i-lucide-loader-circle' : 'i-lucide-user-round'"
                class="size-4"
                :class="profileSwitchPending ? 'animate-spin' : undefined"
              />
            </template>
          </USelectMenu>

          <div class="grid grid-cols-2 gap-1.5">
            <UButton
              block
              color="neutral"
              variant="soft"
              size="xs"
              icon="i-lucide-plus"
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
        </div>

        <SidebarSessionGroups
          :groups="groupedSessions"
          :active-session-id="typeof route.params.id === 'string' ? route.params.id : undefined"
          :pending-session-id="pendingSessionId"
          :now="now"
          :read-message-counts="readMessageCounts"
          :read-message-counts-loaded="readMessageCountsLoaded"
          :is-session-running="isSessionRunning"
          :has-prompt-unread="hasPromptUnread"
          @edit-workspace="beginEditWorkspace"
          @start-workspace-chat="startWorkspaceChat"
          @open-session="openSession"
          @rename-session="beginRename"
          @confirm-session-action="beginConfirmAction"
        />
      </template>
    </UDashboardSidebar>

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
