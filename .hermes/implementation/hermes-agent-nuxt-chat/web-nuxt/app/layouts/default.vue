<script setup lang="ts">
const api = useHermesApi()
const route = useRoute()

const { data, refresh } = await useAsyncData('web-chat-sessions', () => api.listSessions())

const items = computed(() => [
  [
    {
      label: 'New chat',
      icon: 'i-lucide-plus',
      to: '/'
    }
  ],
  (data.value?.sessions || []).map(session => ({
    label: session.title || session.preview || 'Untitled chat',
    description: session.preview,
    icon: 'i-lucide-message-square',
    to: `/chat/${session.id}`,
    active: route.params.id === session.id
  }))
])

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
        <UNavigationMenu :items="items" orientation="vertical" class="px-2" />
      </template>
    </UDashboardSidebar>

    <slot />
  </UDashboardGroup>
</template>
