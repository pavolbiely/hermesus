<script setup lang="ts">
const api = useHermesApi()
const route = useRoute()

const { data, refresh } = await useAsyncData('web-chat-sessions', () => api.listSessions())

const sessions = computed(() => data.value?.sessions || [])
const now = ref(new Date())
let timer: ReturnType<typeof setInterval> | undefined

function sessionTime(updatedAt: string) {
  return formatCompactRelativeTime(updatedAt, now.value)
}

function sessionTimestampTitle(updatedAt: string) {
  const timestamp = new Date(updatedAt).getTime()

  return Number.isFinite(timestamp) ? new Date(timestamp).toLocaleString() : undefined
}

onMounted(() => {
  timer = setInterval(() => {
    now.value = new Date()
  }, 60_000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})

provide('refreshSessions', refresh)
</script>

<template>
  <UDashboardGroup>
    <UDashboardSidebar collapsible resizable>
      <template #header>
        <div class="flex items-center gap-2 px-2 py-1.5">
          <UIcon name="i-lucide-sparkles" class="size-5 text-primary" />
          <span class="font-semibold">Hermes Agent</span>
        </div>
      </template>

      <template #default>
        <nav class="space-y-1 px-2" aria-label="Chat sessions">
          <UButton
            to="/"
            icon="i-lucide-plus"
            label="New chat"
            color="neutral"
            variant="ghost"
            block
            class="justify-start"
          />

          <div class="pt-2">
            <NuxtLink
              v-for="session in sessions"
              :key="session.id"
              :to="`/chat/${session.id}`"
              class="flex min-w-0 items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-elevated"
              :class="route.params.id === session.id ? 'bg-elevated text-highlighted' : 'text-default'"
            >
              <UIcon name="i-lucide-message-square" class="size-4 shrink-0 text-muted" />
              <span class="min-w-0 flex-1 truncate">
                {{ session.title || session.preview || 'Untitled chat' }}
              </span>
              <span class="shrink-0 text-xs text-muted" :title="sessionTimestampTitle(session.updatedAt)">
                {{ sessionTime(session.updatedAt) }}
              </span>
            </NuxtLink>
          </div>
        </nav>
      </template>
    </UDashboardSidebar>

    <slot />
  </UDashboardGroup>
</template>
