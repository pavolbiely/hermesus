<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'
import type { SessionGroup } from '~/utils/sessionGroups'
import type { WebChatSession, WebChatWorkspace } from '~/types/web-chat'
import { isSessionUnread } from '~/utils/chatReadReceipts'

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
  confirmSessionAction: [action: 'duplicate' | 'delete', session: WebChatSession]
}>()

const openMenuSessionId = ref<string | null>(null)
const contextMenuReference = shallowRef<{ getBoundingClientRect: () => DOMRect } | null>(null)

function sessionTitle(session: WebChatSession) {
  return session.title || session.preview || 'Untitled chat'
}

function sessionTime(updatedAt: string) {
  return formatCompactRelativeTime(updatedAt, props.now)
}

function sessionTimestampTitle(updatedAt: string) {
  const timestamp = new Date(updatedAt).getTime()

  return Number.isFinite(timestamp) ? new Date(timestamp).toLocaleString() : undefined
}

function isActiveSession(session: WebChatSession) {
  return props.activeSessionId === session.id
}

function isUnreadSession(session: WebChatSession) {
  return isSessionUnread(
    session,
    props.readMessageCounts,
    props.readMessageCountsLoaded,
    props.hasLocalUnread?.(session) || false
  )
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

function confirmSessionAction(action: 'duplicate' | 'delete', session: WebChatSession) {
  openMenuSessionId.value = null
  contextMenuReference.value = null
  emit('confirmSessionAction', action, session)
}

function sessionActionItems(session: WebChatSession): DropdownMenuItem[] {
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
      label: 'Delete',
      icon: 'i-lucide-trash-2',
      color: 'error',
      onSelect: () => confirmSessionAction('delete', session)
    }
  ]
}
</script>

<template>
  <nav class="space-y-4 px-2" aria-label="Chat sessions by workspace">
    <section v-for="group in groups" :key="group.id" class="space-y-1">
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
                @click.stop="emit('editWorkspace', group.workspace)"
              />
            </UTooltip>
          </div>
          <UTooltip v-if="group.path" :text="`New chat`">
            <UButton
              :aria-label="`New chat in ${group.label}`"
              icon="i-lucide-plus"
              color="neutral"
              variant="ghost"
              size="xs"
              square
              @click.stop="emit('startWorkspaceChat', group.path)"
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
          class="group relative flex h-8 w-full min-w-0 cursor-pointer items-center gap-1 rounded-md px-2 text-left text-sm outline-none hover:bg-elevated focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1 focus-within:bg-elevated"
          :class="[
            isActiveSession(session) ? 'bg-elevated text-highlighted' : 'text-default',
            isUnreadSession(session) ? 'font-bold text-black dark:text-white' : 'font-normal'
          ]"
          @click="emit('openSession', session)"
          @pointerenter="emit('prefetchSession', session)"
          @focus="emit('prefetchSession', session)"
          @keydown.enter.prevent="emit('openSession', session)"
          @keydown.space.prevent="emit('openSession', session)"
          @dblclick.stop.prevent="isActiveSession(session) && renameSession(session)"
          @contextmenu.prevent="openSessionContextMenu(session, $event)"
        >
          <span v-if="isUnreadSession(session)" class="absolute inset-y-0 left-2 flex items-center" aria-hidden="true">
            <span class="block size-1.5 rounded-full bg-primary" />
          </span>
          <UIcon
            v-if="session.pinned"
            name="i-lucide-pin"
            class="size-3.5 shrink-0 text-muted"
            :class="isUnreadSession(session) ? 'ml-4' : undefined"
            aria-hidden="true"
          />
          <span class="min-w-0 flex-1 truncate" :class="isUnreadSession(session) && !session.pinned ? 'pl-4' : undefined">
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
              class="absolute right-1 text-xs text-muted group-hover:opacity-0 group-focus-within:opacity-0"
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
