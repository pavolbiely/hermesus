<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'
import type { SessionGroup } from '~/utils/sessionGroups'
import type { WebChatSession, WebChatSessionPreviewResponse, WebChatWorkspace } from '~/types/web-chat'
import { isSessionUnread } from '~/utils/chatReadReceipts'
import { displayedGroupSessions, hiddenGroupSessionCount, MAX_COLLAPSED_SESSION_COUNT, sessionTitle, sortedGroupSessions } from '~/utils/sidebarSessions'

const props = defineProps<{
  groups: SessionGroup[]
  activeSessionId?: string
  pendingSessionId?: string | null
  now: Date
  readMessageCounts: Record<string, number>
  readMessageCountsLoaded: boolean
  isSessionRunning: (session: WebChatSession) => boolean
  hasLocalUnread?: (session: WebChatSession) => boolean
}>()

const emit = defineEmits<{
  editWorkspace: [workspace: WebChatWorkspace]
  startWorkspaceChat: [path: string]
  openSession: [session: WebChatSession]
  prefetchSession: [session: WebChatSession]
  renameSession: [session: WebChatSession]
  toggleSessionPinned: [session: WebChatSession]
  restoreSession: [session: WebChatSession]
  confirmSessionAction: [action: 'duplicate' | 'archive' | 'delete', session: WebChatSession]
  reorderWorkspaces: [workspaceIds: string[]]
}>()

const OTHER_CHATS_GROUP_ID = '__other__'
const COLLAPSED_GROUPS_STORAGE_KEY = 'hermes-chat-collapsed-session-groups'

const openMenuSessionId = ref<string | null>(null)
const api = useHermesApi()
type PreviewState = {
  data?: WebChatSessionPreviewResponse
  loading?: boolean
  generating?: boolean
  error?: string
}
const previewStates = ref<Record<string, PreviewState>>({})
const draggingWorkspaceId = ref<string | null>(null)
const dragPreviewWorkspaceIds = ref<string[] | null>(null)
const preserveDroppedPreview = ref(false)
const suppressNextWorkspaceClick = ref(false)
const contextMenuReference = shallowRef<{ getBoundingClientRect: () => DOMRect } | null>(null)
const collapsedGroupIds = ref(new Set<string>([OTHER_CHATS_GROUP_ID]))
const expandedSessionGroupIds = ref(new Set<string>())
// Keep chats that were promoted by unread state stable after opening them.
const promotedUnreadSessionIds = ref(new Set<string>())
let clearDroppedPreviewTimer: number | undefined

function sessionTime(updatedAt: string) {
  return formatCompactRelativeTime(updatedAt, props.now)
}

function isActiveSession(session: WebChatSession) {
  return props.activeSessionId === session.id
}

function previewState(session: WebChatSession) {
  return previewStates.value[session.id] || {}
}

function setPreviewState(sessionId: string, state: PreviewState) {
  previewStates.value = {
    ...previewStates.value,
    [sessionId]: {
      ...previewStates.value[sessionId],
      ...state
    }
  }
}

function sessionPreviewSummary(session: WebChatSession) {
  const state = previewState(session)
  return state.data?.summary?.trim() || ''
}

function suppressNativeTitleTooltip(event: Event) {
  const element = event.currentTarget
  if (!(element instanceof HTMLElement)) return

  element.setAttribute('title', '')
  for (const titledElement of element.querySelectorAll<HTMLElement>('[title]')) {
    titledElement.setAttribute('title', '')
  }
}

function loadSessionPreviewOnOpen(session: WebChatSession, open: boolean) {
  if (!open) return
  emit('prefetchSession', session)
  if (!previewState(session).data && !previewState(session).loading) {
    void loadSessionPreview(session.id)
  }
}

async function loadSessionPreview(sessionId: string) {
  setPreviewState(sessionId, { loading: true, error: undefined })
  try {
    const data = await api.getSessionPreview(sessionId)
    setPreviewState(sessionId, { data, loading: false, error: undefined })
  } catch (error) {
    setPreviewState(sessionId, { loading: false, error: error instanceof Error ? error.message : 'Failed to load summary' })
  }
}

async function generateSessionPreview(session: WebChatSession) {
  setPreviewState(session.id, { generating: true, error: undefined })
  try {
    const data = await api.generateSessionPreviewSummary(session.id)
    setPreviewState(session.id, { data, generating: false, loading: false, error: undefined })
  } catch (error) {
    setPreviewState(session.id, { generating: false, loading: false, error: error instanceof Error ? error.message : 'Failed to generate summary' })
  }
}

function isSortableWorkspaceGroup(group: SessionGroup) {
  return Boolean(group.workspace)
}

const displayedGroups = computed(() => {
  const previewIds = dragPreviewWorkspaceIds.value
  if (!previewIds) return props.groups

  const workspaceGroups = new Map(
    props.groups
      .filter(group => group.workspace)
      .map(group => [group.workspace!.id, group])
  )
  const orderedWorkspaceGroups = [
    ...previewIds.map(id => workspaceGroups.get(id)).filter((group): group is SessionGroup => Boolean(group)),
    ...props.groups.filter(group => group.workspace && !previewIds.includes(group.workspace.id))
  ]
  const fixedGroups = props.groups.filter(group => !group.workspace)

  return [...orderedWorkspaceGroups, ...fixedGroups]
})

function workspaceGroupIds() {
  return props.groups
    .map(group => group.workspace?.id)
    .filter((id): id is string => Boolean(id))
}

function startWorkspaceDrag(group: SessionGroup, event: DragEvent) {
  if (!group.workspace) return
  draggingWorkspaceId.value = group.workspace.id
  dragPreviewWorkspaceIds.value = workspaceGroupIds()
  event.dataTransfer?.setData('text/plain', group.workspace.id)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}

function orderedWorkspaceIdsWithMove(sourceId: string, targetId: string, placeAfter: boolean) {
  const workspaceIds = dragPreviewWorkspaceIds.value || workspaceGroupIds()
  const nextWorkspaceIds = workspaceIds.filter(id => id !== sourceId)
  const targetIndex = nextWorkspaceIds.indexOf(targetId)
  if (targetIndex === -1) return workspaceIds

  nextWorkspaceIds.splice(targetIndex + (placeAfter ? 1 : 0), 0, sourceId)
  return nextWorkspaceIds
}

function dragOverWorkspace(group: SessionGroup, event: DragEvent) {
  const sourceId = draggingWorkspaceId.value
  const targetId = group.workspace?.id
  if (!sourceId || !targetId) return

  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
  if (sourceId === targetId) return

  const bounds = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const nextWorkspaceIds = orderedWorkspaceIdsWithMove(sourceId, targetId, event.clientY > bounds.top + bounds.height / 2)
  if (nextWorkspaceIds.join('\0') !== dragPreviewWorkspaceIds.value?.join('\0')) {
    dragPreviewWorkspaceIds.value = nextWorkspaceIds
  }
}

function dropWorkspace(group: SessionGroup, event: DragEvent) {
  event.preventDefault()
  const sourceId = draggingWorkspaceId.value
  const targetId = group.workspace?.id
  if (!sourceId || !targetId) {
    endWorkspaceDrag()
    return
  }

  const workspaceIds = dragPreviewWorkspaceIds.value || orderedWorkspaceIdsWithMove(sourceId, targetId, false)
  preserveDroppedPreview.value = true
  if (clearDroppedPreviewTimer) clearTimeout(clearDroppedPreviewTimer)
  clearDroppedPreviewTimer = window.setTimeout(() => {
    preserveDroppedPreview.value = false
    dragPreviewWorkspaceIds.value = null
  }, 1000)
  emit('reorderWorkspaces', workspaceIds)
  endWorkspaceDrag()
}

function endWorkspaceDrag() {
  if (draggingWorkspaceId.value) {
    suppressNextWorkspaceClick.value = true
    window.setTimeout(() => {
      suppressNextWorkspaceClick.value = false
    })
  }
  draggingWorkspaceId.value = null
  if (!preserveDroppedPreview.value) {
    dragPreviewWorkspaceIds.value = null
  }
}

function toggleWorkspaceGroup(group: SessionGroup) {
  if (suppressNextWorkspaceClick.value) return
  toggleGroupCollapsed(group)
}

function isUnreadSession(session: WebChatSession) {
  return isSessionUnread(
    session,
    props.readMessageCounts,
    props.readMessageCountsLoaded,
    props.hasLocalUnread?.(session) || false
  )
}

function isPromotedUnreadSession(session: WebChatSession) {
  return isUnreadSession(session) || promotedUnreadSessionIds.value.has(session.id)
}

function sortedSessions(group: SessionGroup) {
  return sortedGroupSessions(group, isPromotedUnreadSession)
}

function isSessionGroupExpanded(group: SessionGroup) {
  return expandedSessionGroupIds.value.has(group.id)
}

function displayedSessions(group: SessionGroup) {
  return displayedGroupSessions(group, isSessionGroupExpanded(group), isPromotedUnreadSession)
}

function hiddenSessionCount(group: SessionGroup) {
  return hiddenGroupSessionCount(group, isSessionGroupExpanded(group))
}

function toggleSessionGroupExpanded(group: SessionGroup) {
  const nextExpandedGroupIds = new Set(expandedSessionGroupIds.value)
  if (nextExpandedGroupIds.has(group.id)) {
    nextExpandedGroupIds.delete(group.id)
  } else {
    nextExpandedGroupIds.add(group.id)
  }
  expandedSessionGroupIds.value = nextExpandedGroupIds
}

function isGroupCollapsed(group: SessionGroup) {
  return collapsedGroupIds.value.has(group.id)
}

function readCollapsedGroupIds() {
  if (!import.meta.client) return new Set<string>([OTHER_CHATS_GROUP_ID])

  try {
    const raw = window.localStorage.getItem(COLLAPSED_GROUPS_STORAGE_KEY)
    if (!raw) return new Set<string>([OTHER_CHATS_GROUP_ID])

    const value = JSON.parse(raw)
    if (!Array.isArray(value)) return new Set<string>([OTHER_CHATS_GROUP_ID])

    return new Set(value.filter((id): id is string => typeof id === 'string'))
  } catch {
    return new Set<string>([OTHER_CHATS_GROUP_ID])
  }
}

function saveCollapsedGroupIds(ids: Set<string>) {
  if (!import.meta.client) return
  window.localStorage.setItem(COLLAPSED_GROUPS_STORAGE_KEY, JSON.stringify([...ids]))
}

function toggleGroupCollapsed(group: SessionGroup) {
  const nextCollapsedGroupIds = new Set(collapsedGroupIds.value)
  if (nextCollapsedGroupIds.has(group.id)) {
    nextCollapsedGroupIds.delete(group.id)
  } else {
    nextCollapsedGroupIds.add(group.id)
  }
  collapsedGroupIds.value = nextCollapsedGroupIds
}

function syncPromotedUnreadSessions() {
  const visibleSessionIds = new Set<string>()
  const nextPromotedSessionIds = new Set(promotedUnreadSessionIds.value)
  let changed = false

  for (const group of props.groups) {
    for (const session of group.sessions) {
      visibleSessionIds.add(session.id)
      if (isUnreadSession(session) && !nextPromotedSessionIds.has(session.id)) {
        nextPromotedSessionIds.add(session.id)
        changed = true
      }
    }
  }

  for (const sessionId of nextPromotedSessionIds) {
    if (!visibleSessionIds.has(sessionId)) {
      nextPromotedSessionIds.delete(sessionId)
      changed = true
    }
  }

  if (changed) promotedUnreadSessionIds.value = nextPromotedSessionIds
}

watch(
  () => props.groups,
  () => {
    const previewIds = dragPreviewWorkspaceIds.value
    if (!preserveDroppedPreview.value || !previewIds) return
    if (workspaceGroupIds().join('\0') !== previewIds.join('\0')) return

    if (clearDroppedPreviewTimer) clearTimeout(clearDroppedPreviewTimer)
    clearDroppedPreviewTimer = undefined
    preserveDroppedPreview.value = false
    dragPreviewWorkspaceIds.value = null
  }
)

watch(
  collapsedGroupIds,
  ids => saveCollapsedGroupIds(ids)
)

watch(
  () => [props.groups, props.readMessageCounts, props.readMessageCountsLoaded] as const,
  syncPromotedUnreadSessions,
  { immediate: true }
)

function expandActiveSessionGroup(activeSessionId = props.activeSessionId) {
  if (!activeSessionId) return

  const activeGroup = props.groups.find(group => group.sessions.some(session => session.id === activeSessionId))
  if (!activeGroup || !collapsedGroupIds.value.has(activeGroup.id)) return

  const nextCollapsedGroupIds = new Set(collapsedGroupIds.value)
  nextCollapsedGroupIds.delete(activeGroup.id)
  collapsedGroupIds.value = nextCollapsedGroupIds
}

function revealActiveSession(activeSessionId = props.activeSessionId) {
  if (!activeSessionId) return

  const activeGroup = props.groups.find(group => group.sessions.some(session => session.id === activeSessionId))
  if (!activeGroup || expandedSessionGroupIds.value.has(activeGroup.id)) return

  const activeIndex = sortedSessions(activeGroup).findIndex(session => session.id === activeSessionId)
  if (activeIndex < MAX_COLLAPSED_SESSION_COUNT) return

  const nextExpandedGroupIds = new Set(expandedSessionGroupIds.value)
  nextExpandedGroupIds.add(activeGroup.id)
  expandedSessionGroupIds.value = nextExpandedGroupIds
}

watch(
  () => [props.activeSessionId, props.groups] as const,
  ([activeSessionId]) => {
    expandActiveSessionGroup(activeSessionId)
    revealActiveSession(activeSessionId)
  },
  { immediate: true }
)

onMounted(() => {
  collapsedGroupIds.value = readCollapsedGroupIds()
  expandActiveSessionGroup()
  revealActiveSession()
})

onUnmounted(() => {
  if (clearDroppedPreviewTimer) clearTimeout(clearDroppedPreviewTimer)
})

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

function renameSession(session: WebChatSession) {
  openMenuSessionId.value = null
  contextMenuReference.value = null
  emit('renameSession', session)
}

function toggleSessionPinned(session: WebChatSession) {
  openMenuSessionId.value = null
  contextMenuReference.value = null
  emit('toggleSessionPinned', session)
}

function restoreSession(session: WebChatSession) {
  openMenuSessionId.value = null
  contextMenuReference.value = null
  emit('restoreSession', session)
}

function confirmSessionAction(action: 'duplicate' | 'archive' | 'delete', session: WebChatSession) {
  openMenuSessionId.value = null
  contextMenuReference.value = null
  emit('confirmSessionAction', action, session)
}

function sessionActionItems(session: WebChatSession): DropdownMenuItem[] {
  if (session.archived) {
    return [
      {
        label: 'Restore',
        icon: 'i-lucide-archive-restore',
        onSelect: () => restoreSession(session)
      },
      {
        label: 'Delete permanently',
        icon: 'i-lucide-trash-2',
        color: 'error',
        onSelect: () => confirmSessionAction('delete', session)
      }
    ]
  }

  return [
    {
      label: session.pinned ? 'Unpin' : 'Pin',
      icon: session.pinned ? 'i-lucide-pin-off' : 'i-lucide-pin',
      onSelect: () => toggleSessionPinned(session)
    },
    {
      label: 'Rename',
      icon: 'i-lucide-pencil',
      onSelect: () => renameSession(session)
    },
    {
      label: 'Duplicate',
      icon: 'i-lucide-copy',
      onSelect: () => confirmSessionAction('duplicate', session)
    },
    {
      label: 'Archive',
      icon: 'i-lucide-archive',
      onSelect: () => confirmSessionAction('archive', session)
    }
  ]
}
</script>

<template>
  <TransitionGroup
    tag="nav"
    name="workspace-sort"
    class="space-y-4 px-0.5"
    aria-label="Chat sessions by workspace"
  >
    <section
      v-for="group in displayedGroups"
      :key="group.id"
      class="space-y-1"
      @dragover="dragOverWorkspace(group, $event)"
      @drop="dropWorkspace(group, $event)"
    >
      <div
        role="button"
        tabindex="0"
        class="group/workspace flex h-7 w-full min-w-0 cursor-pointer items-center justify-between gap-2 rounded-md px-1.5 text-left text-xs font-medium uppercase tracking-wide text-muted outline-none hover:bg-elevated focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1"
        :class="[
          isSortableWorkspaceGroup(group) ? 'cursor-grab active:cursor-grabbing' : '',
          draggingWorkspaceId === group.workspace?.id ? 'opacity-50' : ''
        ]"
        :aria-expanded="!isGroupCollapsed(group)"
        :draggable="isSortableWorkspaceGroup(group)"
        @click="toggleWorkspaceGroup(group)"
        @dragstart="startWorkspaceDrag(group, $event)"
        @dragend="endWorkspaceDrag"
        @keydown.enter.prevent="toggleWorkspaceGroup(group)"
        @keydown.space.prevent="toggleWorkspaceGroup(group)"
      >
        <span class="flex min-w-0 items-center gap-1.5 truncate">
          <UIcon
            :key="isGroupCollapsed(group) ? 'folder' : 'folder-open'"
            :name="isGroupCollapsed(group) ? 'i-lucide-folder' : 'i-lucide-folder-open'"
            class="size-3.5 shrink-0 text-muted"
          />
          <span class="min-w-0 truncate">{{ group.label }}</span>
        </span>
        <div class="flex shrink-0 items-center gap-3.5 opacity-0 transition-opacity group-hover/workspace:opacity-100 group-focus-within/workspace:opacity-100">
          <UTooltip v-if="group.workspace" text="Edit workspace">
            <UButton
              :aria-label="`Edit ${group.label}`"
              icon="i-lucide-pencil"
              color="neutral"
              variant="ghost"
              size="xs"
              square
              class="size-3.5"
              :ui="{ leadingIcon: 'size-3.5' }"
              @click.stop="emit('editWorkspace', group.workspace)"
            />
          </UTooltip>
          <UTooltip v-if="group.path" :text="`New chat`">
            <UButton
              :aria-label="`New chat in ${group.label}`"
              icon="i-lucide-square-pen"
              color="neutral"
              variant="ghost"
              size="xs"
              square
              class="mr-2.5 size-3.5"
              :ui="{ leadingIcon: 'size-3.5' }"
              @click.stop="emit('startWorkspaceChat', group.path)"
            />
          </UTooltip>
        </div>
      </div>

      <div v-if="group.sessions.length && !isGroupCollapsed(group)" class="space-y-1">
        <UPopover
          v-for="session in displayedSessions(group)"
          :key="session.id"
          mode="hover"
          class="block w-full"
          :open-delay="1000"
          :close-delay="100"
          :content="{ side: 'right', align: 'start', sideOffset: 8 }"
          @update:open="loadSessionPreviewOnOpen(session, $event)"
        >
          <div
            role="button"
            tabindex="0"
            title=""
            class="group relative flex h-8 w-full min-w-0 cursor-pointer items-center gap-1 rounded-md px-1.5 text-left text-sm outline-none hover:bg-elevated focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1 focus-within:bg-elevated"
            :class="[
              isActiveSession(session) ? 'bg-elevated text-highlighted' : 'text-default',
              isUnreadSession(session) ? 'font-bold text-black dark:text-white' : 'font-normal'
            ]"
            @pointerenter.capture="suppressNativeTitleTooltip"
            @mouseenter.capture="suppressNativeTitleTooltip"
            @focus.capture="suppressNativeTitleTooltip"
            @click="emit('openSession', session)"
            @keydown.enter.prevent="emit('openSession', session)"
            @keydown.space.prevent="emit('openSession', session)"
            @dblclick.stop.prevent="isActiveSession(session) && renameSession(session)"
            @contextmenu.prevent="openSessionContextMenu(session, $event)"
          >
            <span
              class="flex size-3.5 shrink-0 items-center justify-center"
              aria-hidden="true"
            >
              <span v-if="isUnreadSession(session)" class="block size-1.5 rounded-full bg-primary" />
              <UIcon
                v-else-if="session.pinned"
                name="i-lucide-pin"
                class="size-3.5 text-muted"
              />
            </span>
            <span class="min-w-0 flex-1 truncate" title="">
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
                  icon="i-lucide-ellipsis-vertical"
                  loading-icon="i-lucide-cpu"
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
                name="i-lucide-cpu"
                class="absolute right-1 size-3.5 animate-spin text-muted group-hover:opacity-0 group-focus-within:opacity-0"
              />

              <span
                v-else-if="openMenuSessionId !== session.id"
                class="absolute right-1 text-xs text-muted group-hover:opacity-0 group-focus-within:opacity-0"
              >
                {{ sessionTime(session.updatedAt) }}
              </span>
            </div>
          </div>

          <template #content>
            <div class="w-80 p-3 text-sm">
              <div class="truncate font-medium text-highlighted">
                {{ sessionTitle(session) }}
              </div>
              <p v-if="sessionPreviewSummary(session)" class="mt-2 text-sm leading-5 text-muted">
                {{ sessionPreviewSummary(session) }}
              </p>
              <div v-else class="mt-2 space-y-2">
                <p class="text-sm leading-5 text-muted">
                  {{ previewState(session).loading ? 'Loading summary…' : 'No summary cached yet.' }}
                </p>
                <p v-if="previewState(session).error" class="text-xs text-error">
                  {{ previewState(session).error }}
                </p>
                <UButton
                  size="xs"
                  color="neutral"
                  variant="soft"
                  loading-icon="i-lucide-cpu"
                  :loading="previewState(session).generating"
                  :label="previewState(session).error ? 'Retry summary' : 'Generate summary'"
                  @click.stop="generateSessionPreview(session)"
                />
              </div>
            </div>
          </template>
        </UPopover>

        <UButton
          v-if="group.sessions.length > MAX_COLLAPSED_SESSION_COUNT"
          :label="isSessionGroupExpanded(group) ? 'Show less' : `Show ${hiddenSessionCount(group)} more`"
          :aria-expanded="isSessionGroupExpanded(group)"
          color="neutral"
          variant="ghost"
          size="xs"
          class="ml-4 h-7 px-1.5 text-xs text-muted hover:text-default"
          :trailing-icon="isSessionGroupExpanded(group) ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
          @click="toggleSessionGroupExpanded(group)"
        />
      </div>

      <p v-else-if="!isGroupCollapsed(group)" class="px-1.5 text-xs text-muted">
        No chats yet
      </p>
    </section>
  </TransitionGroup>
</template>

<style scoped>
.workspace-sort-move {
  transition: transform 150ms ease;
}
</style>
