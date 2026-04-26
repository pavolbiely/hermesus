<script setup lang="ts">
const input = ref('')
const loading = ref(false)
const error = ref<Error | undefined>()
const api = useHermesApi()
const router = useRouter()
const refreshSessions = inject<() => Promise<void> | void>('refreshSessions')

async function onSubmit() {
  const message = input.value.trim()
  if (!message || loading.value) return

  loading.value = true
  error.value = undefined
  try {
    const result = await api.startRun(message)
    await router.push({ path: `/chat/${result.sessionId}`, query: { run: result.runId } })
    void refreshSessions?.()
  } catch (err) {
    error.value = err instanceof Error ? err : new Error('Failed to create chat')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <UDashboardPanel>
    <template #header>
      <UDashboardNavbar title="New chat" />
    </template>

    <template #body>
      <UContainer class="flex min-h-full items-center justify-center py-12">
        <div class="w-full max-w-3xl space-y-6">
          <div class="space-y-2 text-center">
            <h1 class="text-3xl font-semibold tracking-tight">How can Hermes help?</h1>
            <p class="text-muted">Start a native web chat session backed by Hermes Agent.</p>
          </div>

          <UChatPrompt v-model="input" :error="error" @submit="onSubmit">
            <UChatPromptSubmit :status="loading ? 'submitted' : 'ready'" />
          </UChatPrompt>
        </div>
      </UContainer>
    </template>
  </UDashboardPanel>
</template>
