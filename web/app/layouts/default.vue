<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'
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
const openMenuSessionId = ref<string | null>(null)
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
const contextMenuReference = shallowRef<{ getBoundingClientRect: () => DOMRect } | null>(null)
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

function sessionTime(updatedAt: string) {
  return formatCompactRelativeTime(updatedAt, now.value)
}

function sessionTimestampTitle(updatedAt: string) {
  const timestamp = new Date(updatedAt).getTime()

  return Number.isFinite(timestamp) ? new Date(timestamp).toLocaleString() : undefined
}

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

function markSessionRead(session: WebChatSession) {
  if (!readMessageCountsLoaded.value) return
  const currentCount = Math.max(0, session.messageCount || 0)
  if (readMessageCounts.value[session.id] === currentCount) return
  readMessageCounts.value = { ...readMessageCounts.value, [session.id]: currentCount }
  saveReadMessageCounts()
}

function syncReadMessageCounts() {
  if (!readMessageCountsLoaded.value) return

  let changed = false
  const next = { ...readMessageCounts.value }
  const sessionIds = new Set(sessions.value.map(session => session.id))

  for (const session of sessions.value) {
    if (isActiveSession(session) || next[session.id] === undefined) {
      next[session.id] = Math.max(0, session.messageCount || 0)
      changed = true
    }
  }

  for (const id of Object.keys(next)) {
    if (!sessionIds.has(id)) {
      delete next[id]
      changed = true
    }
  }

  if (!changed) return
  readMessageCounts.value = next
  saveReadMessageCounts()
}

function isUnreadSession(session: WebChatSession) {
  if (isActiveSession(session) || !readMessageCountsLoaded.value) return false
  return (session.messageCount || 0) > (readMessageCounts.value[session.id] || 0)
}

function isSessionRunning(session: WebChatSession) {
  return activeChatRuns.isRunning(session.id)
}

function beginRename(session: WebChatSession) {
  renameSession.value = session
  renameTitle.value = sessionTitle(session)
  openMenuSessionId.value = null
  contextMenuReference.value = null
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
  openMenuSessionId.value = null
  contextMenuReference.value = null
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
  markSessionRead(session)
  void router.push(`/chat/${session.id}`)
}

function onSessionDoubleClick(session: WebChatSession) {
  if (!isActiveSession(session)) return
  beginRename(session)
}

function openSessionMenu(session: WebChatSession) {
  contextMenuReference.value = null
  openMenuSessionId.value = session.id
}

function openSessionContextMenu(session: WebChatSession, event: MouseEvent) {
  const { clientX, clientY } = event
  contextMenuReference.value = {
    getBoundingClientRect: () => new DOMRect(clientX, clientY, 0, 0)
  }
  openMenuSessionId.value = session.id
}

function closeSessionMenu(open: boolean, session: WebChatSession) {
  openMenuSessionId.value = open ? session.id : null
  if (!open) contextMenuReference.value = null
}

function sessionMenuContent(session: WebChatSession) {
  if (contextMenuReference.value && openMenuSessionId.value === session.id) {
    return {
      reference: contextMenuReference.value,
      align: 'start' as const,
      side: 'bottom' as const,
      sideOffset: 0
    }
  }

  return { align: 'end' as const, side: 'right' as const, sideOffset: 6 }
}

function actionButtonClass(session: WebChatSession) {
  return openMenuSessionId.value === session.id
    ? 'opacity-100'
    : 'opacity-0 group-hover:opacity-100 group-focus-within:opacity-100'
}

function sessionActionItems(session: WebChatSession): DropdownMenuItem[] {
  return [
    {
      label: 'Rename',
      icon: 'i-lucide-pencil',
      onSelect: () => beginRename(session)
    },
    {
      label: 'Duplicate',
      icon: 'i-lucide-copy',
      onSelect: () => beginConfirmAction('duplicate', session)
    },
    {
      label: 'Delete',
      icon: 'i-lucide-trash-2',
      color: 'error',
      onSelect: () => beginConfirmAction('delete', session)
    }
  ]
}

watch(
  () => [route.params.id, sessions.value.map(session => `${session.id}:${session.messageCount}`).join('|')],
  () => syncReadMessageCounts()
)

onMounted(() => {
  loadReadMessageCounts()
  syncReadMessageCounts()
  timer = setInterval(() => {
    now.value = new Date()
  }, 60_000)
  unsubscribeRunFinished = activeChatRuns.onFinished(() => refresh())
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  if (workspaceDirectorySuggestionTimer) clearTimeout(workspaceDirectorySuggestionTimer)
  unsubscribeRunFinished?.()
})

provide('refreshSessions', refresh)
</script>

<template>
  <UDashboardGroup>
    <UDashboardSidebar collapsible :default-size="20">
      <template #header>
        <NuxtLink to="/" class="flex h-8 shrink-0 items-center gap-2 px-2">
          <UIcon name="i-lucide-sparkles" class="size-5 shrink-0 text-primary" />
          <span class="truncate font-semibold">Hermes Agent</span>
        </NuxtLink>
      </template>

      <template #default>
        <div class="space-y-2 px-2 pb-3 pt-1">
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

          <div class="grid grid-cols-2 gap-2">
            <UButton
              block
              color="neutral"
              variant="soft"
              icon="i-lucide-plus"
              label="Chat"
              @click="startNewChat"
            />
            <UButton
              block
              color="neutral"
              variant="soft"
              icon="i-lucide-folder-plus"
              label="Workspace"
              @click="beginCreateWorkspace"
            />
          </div>
        </div>

        <nav class="space-y-4 px-2" aria-label="Chat sessions by workspace">
          <section v-for="group in groupedSessions" :key="group.id" class="space-y-1">
            <div class="group/workspace flex h-7 min-w-0 items-center justify-between gap-2 px-2 text-xs font-medium uppercase tracking-wide text-muted">
              <span class="flex min-w-0 items-center gap-1.5 truncate" :title="group.path || undefined">
                <UIcon
                  name="i-lucide-folder"
                  class="size-3.5 shrink-0 text-muted"
                />
                <span class="min-w-0 truncate">{{ group.label }}</span>
              </span>
              <div class="flex shrink-0 items-center gap-1">
                <div class="opacity-0 transition-opacity group-hover/workspace:opacity-100 group-focus-within/workspace:opacity-100">
                  <UTooltip v-if="group.workspace" text="Edit workspace">
                    <UButton
                      :aria-label="`Edit ${group.label}`"
                      icon="i-lucide-pencil"
                      color="neutral"
                      variant="ghost"
                      size="xs"
                      square
                      @click.stop="beginEditWorkspace(group.workspace)"
                    />
                  </UTooltip>
                </div>
                <UTooltip v-if="group.path" :text="`New chat in ${group.label}`">
                  <UButton
                    :aria-label="`New chat in ${group.label}`"
                    icon="i-lucide-plus"
                    color="neutral"
                    variant="ghost"
                    size="xs"
                    square
                    @click.stop="startWorkspaceChat(group.path)"
                  />
                </UTooltip>
              </div>
            </div>

            <div v-if="group.sessions.length" class="space-y-1">
              <div
                v-for="session in group.sessions"
                :key="session.id"
                role="button"
                tabindex="0"
                class="group flex h-8 w-full min-w-0 cursor-pointer items-center gap-1 rounded-md px-2 text-left text-sm outline-none hover:bg-elevated focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1 focus-within:bg-elevated"
                :class="[
                  isActiveSession(session) ? 'bg-elevated text-highlighted' : 'text-default',
                  isUnreadSession(session) ? 'font-semibold text-black dark:text-white' : 'font-normal'
                ]"
                @click="openSession(session)"
                @keydown.enter.prevent="openSession(session)"
                @keydown.space.prevent="openSession(session)"
                @dblclick.stop.prevent="onSessionDoubleClick(session)"
                @contextmenu.prevent="openSessionContextMenu(session, $event)"
              >
                <span v-if="isUnreadSession(session)" class="flex h-full shrink-0 items-center pr-1.5">
                  <UChip
                    standalone
                    size="sm"
                    color="primary"
                    aria-hidden="true"
                  />
                </span>
                <span class="min-w-0 flex-1 truncate">
                  {{ sessionTitle(session) }}
                </span>

                <div class="relative flex h-6 w-10 shrink-0 items-center justify-end">
                  <UDropdownMenu
                    :items="sessionActionItems(session)"
                    :content="sessionMenuContent(session)"
                    size="sm"
                    :open="openMenuSessionId === session.id"
                    @update:open="closeSessionMenu($event, session)"
                  >
                    <UButton
                      aria-label="Chat actions"
                      icon="i-lucide-ellipsis"
                      color="neutral"
                      variant="ghost"
                      size="xs"
                      square
                      class="absolute right-0 z-10 transition-opacity"
                      :class="actionButtonClass(session)"
                      :loading="pendingSessionId === session.id"
                      @click.stop="openSessionMenu(session)"
                    />
                  </UDropdownMenu>

                  <UIcon
                    v-if="isSessionRunning(session) && openMenuSessionId !== session.id"
                    name="i-lucide-loader-circle"
                    class="absolute right-1 size-3.5 animate-spin text-muted group-hover:opacity-0 group-focus-within:opacity-0"
                  />

                  <span
                    v-else-if="openMenuSessionId !== session.id"
                    class="absolute right-0 text-xs text-muted group-hover:opacity-0 group-focus-within:opacity-0"
                    :title="sessionTimestampTitle(session.updatedAt)"
                  >
                    {{ sessionTime(session.updatedAt) }}
                  </span>
                </div>
              </div>
            </div>

            <p v-else class="px-2 text-xs text-muted">
              No chats yet
            </p>
          </section>
        </nav>
      </template>
    </UDashboardSidebar>

    <slot />

    <UModal
      v-model:open="workspaceModalOpen"
      :title="editingWorkspace ? 'Edit workspace' : 'Add workspace'"
      description="Give the workspace a display name and point it at a local project directory."
    >
      <template #body>
        <form class="space-y-4" @submit.prevent="saveWorkspace">
          <UFormField label="Name" required>
            <UInput
              v-model="workspaceLabel"
              autofocus
              placeholder="Hermesum"
              class="w-full"
              :disabled="workspacePending"
              @keydown.esc.prevent="cancelWorkspaceEdit"
            />
          </UFormField>

          <UFormField label="Directory path" required>
            <UInput
              v-model="workspacePath"
              placeholder="/Users/pavolbiely/Sites/hermesum"
              class="w-full font-mono"
              list="workspace-directory-suggestions"
              :disabled="workspacePending"
              @keydown.esc.prevent="cancelWorkspaceEdit"
            />
            <datalist id="workspace-directory-suggestions">
              <option
                v-for="suggestion in workspaceDirectorySuggestions"
                :key="suggestion"
                :value="suggestion"
              />
            </datalist>
          </UFormField>

          <div class="flex items-center justify-between gap-2">
            <UButton
              v-if="editingWorkspace"
              type="button"
              color="error"
              variant="ghost"
              label="Delete"
              :loading="workspacePending"
              @click="deleteWorkspace"
            />
            <span v-else />

            <div class="flex justify-end gap-2">
              <UButton
                type="button"
                color="neutral"
                variant="ghost"
                label="Cancel"
                :disabled="workspacePending"
                @click="cancelWorkspaceEdit"
              />
              <UButton
                type="submit"
                color="primary"
                :label="editingWorkspace ? 'Save' : 'Add workspace'"
                :loading="workspacePending"
                :disabled="!canSaveWorkspace"
              />
            </div>
          </div>
        </form>
      </template>
    </UModal>

    <UModal
      v-model:open="renameModalOpen"
      title="Rename chat"
      description="Choose a new name for this chat."
    >
      <template #body>
        <form class="space-y-4" @submit.prevent="saveRename">
          <UInput
            v-model="renameTitle"
            autofocus
            aria-label="Chat name"
            class="w-full"
            :disabled="pendingSessionId === renameSession?.id"
            @keydown.esc.prevent="cancelRename"
          />

          <div class="flex justify-end gap-2">
            <UButton
              type="button"
              color="neutral"
              variant="ghost"
              label="Cancel"
              :disabled="pendingSessionId === renameSession?.id"
              @click="cancelRename"
            />
            <UButton
              type="submit"
              color="primary"
              label="Rename"
              :loading="pendingSessionId === renameSession?.id"
              :disabled="!canRename"
            />
          </div>
        </form>
      </template>
    </UModal>

    <UModal
      v-model:open="confirmModalOpen"
      :title="confirmTitle"
      :description="confirmDescription"
    >
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton
            type="button"
            color="neutral"
            variant="ghost"
            label="Cancel"
            :disabled="pendingSessionId === confirmSession?.id"
            @click="cancelConfirmAction"
          />
          <UButton
            type="button"
            :color="confirmAction === 'delete' ? 'error' : 'primary'"
            :label="confirmAction === 'delete' ? 'Delete' : 'Duplicate'"
            :loading="pendingSessionId === confirmSession?.id"
            @click="confirmSessionAction"
          />
        </div>
      </template>
    </UModal>
  </UDashboardGroup>
</template>
