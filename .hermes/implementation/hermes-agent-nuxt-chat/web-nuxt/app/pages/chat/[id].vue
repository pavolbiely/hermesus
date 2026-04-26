<script setup lang="ts">
import highlight from '@comark/nuxt/plugins/highlight'
import type { WebChatMessage, WebChatPart } from '~/types/web-chat'

const route = useRoute()
const api = useHermesApi()
const runStream = useHermesRunStream()
const input = ref('')
const messages = ref<WebChatMessage[]>([])
const bottomRef = ref<HTMLElement | null>(null)
const autoScrollEnabled = ref(true)
const connectedRunIds = new Set<string>()
const error = computed(() => runStream.error.value)
const refreshSessions = inject<() => Promise<void> | void>('refreshSessions')

const sessionId = computed(() => String(route.params.id))
const { data, refresh } = await useAsyncData(
  () => `web-chat-session-${sessionId.value}`,
  () => api.getSession(sessionId.value),
  { watch: [sessionId] }
)

watchEffect(() => {
  messages.value = data.value?.messages ? [...data.value.messages] : []
})

const title = computed(() => data.value?.session.title || 'Chat')
const chatStatus = computed(() => runStream.status.value === 'ready' ? 'ready' : 'streaming')
const isRunning = computed(() => runStream.status.value !== 'ready' && runStream.status.value !== 'error')

function partText(part: WebChatPart) {
  return typeof part.text === 'string' ? part.text : ''
}

function isThinkingMessage(message: WebChatMessage) {
  return message.role === 'assistant' && message.parts.some(part => part.status === 'thinking') && isRunning.value
}

function createThinkingMessage() {
  const message = createLocalMessage('assistant', '')
  message.parts = [{ type: 'text', text: '', status: 'thinking' }]
  return message
}

function ensureThinkingMessage() {
  const lastMessage = messages.value.at(-1)
  if (lastMessage?.role === 'assistant') return
  messages.value.push(createThinkingMessage())
}

function scrollToBottom(behavior: ScrollBehavior = 'smooth') {
  if (!autoScrollEnabled.value) return
  bottomRef.value?.scrollIntoView({ block: 'end', behavior })
}

function isNearBottom() {
  const scrollTop = window.scrollY || document.documentElement.scrollTop
  return window.innerHeight + scrollTop >= document.documentElement.scrollHeight - 80
}

const scrollKeys = new Set(['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '])

function pauseAutoScroll(event?: Event) {
  if (!isRunning.value) return
  if (event instanceof KeyboardEvent && !scrollKeys.has(event.key)) return
  if (event?.type === 'scroll' && isNearBottom()) return
  autoScrollEnabled.value = false
}

function scheduleAutoScroll(behavior: ScrollBehavior = 'smooth') {
  nextTick(() => scrollToBottom(behavior))
}

function appendAssistantDelta(content: string) {
  if (!content) return

  let assistant = messages.value[messages.value.length - 1]
  if (!assistant || assistant.role !== 'assistant') {
    assistant = createLocalMessage('assistant', '')
    messages.value.push(assistant)
  }

  const textPart = assistant.parts.find(part => part.type === 'text')
  if (textPart) {
    textPart.text = textPart.status === 'thinking' ? content : `${textPart.text || ''}${content}`
    textPart.status = null
  } else {
    assistant.parts.push({ type: 'text', text: content })
  }

  scheduleAutoScroll()
}

function replaceAssistantMessage(content?: string) {
  if (!content) return

  const assistant = messages.value[messages.value.length - 1]
  if (assistant?.role === 'assistant') {
    assistant.parts = [{ type: 'text', text: content, status: null }]
    scheduleAutoScroll()
  }
}

function connectRun(runId: string) {
  connectedRunIds.add(runId)
  ensureThinkingMessage()
  scheduleAutoScroll()
  runStream.connect(runId, {
    onDelta: appendAssistantDelta,
    onCompleted: replaceAssistantMessage,
    async onFinished() {
      await refresh()
      await refreshSessions?.()
    }
  })
}

watch(
  () => [route.query.run, data.value?.session.id] as const,
  ([runId]) => {
    if (typeof runId !== 'string' || connectedRunIds.has(runId) || !data.value) return
    autoScrollEnabled.value = true
    connectRun(runId)
  },
  { immediate: true }
)

async function onSubmit() {
  const message = input.value.trim()
  if (!message || runStream.status.value !== 'ready') return

  input.value = ''
  autoScrollEnabled.value = true
  runStream.status.value = 'submitted'
  messages.value.push(createLocalMessage('user', message))
  messages.value.push(createThinkingMessage())
  scheduleAutoScroll()

  try {
    const run = await api.startRun(message, sessionId.value)
    connectRun(run.runId)
  } catch (err) {
    if (messages.value.at(-1)?.role === 'assistant' && messages.value.at(-1)?.parts.some(part => part.status === 'thinking')) {
      messages.value.pop()
    }
    runStream.error.value = err instanceof Error ? err : new Error('Failed to send message')
    runStream.status.value = 'error'
  }
}

onMounted(() => {
  window.addEventListener('scroll', pauseAutoScroll, { passive: true })
  window.addEventListener('wheel', pauseAutoScroll, { passive: true })
  window.addEventListener('touchmove', pauseAutoScroll, { passive: true })
  window.addEventListener('keydown', pauseAutoScroll)
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', pauseAutoScroll)
  window.removeEventListener('wheel', pauseAutoScroll)
  window.removeEventListener('touchmove', pauseAutoScroll)
  window.removeEventListener('keydown', pauseAutoScroll)
})
</script>

<template>
  <UDashboardPanel>
    <template #header>
      <UDashboardNavbar :title="title" />
    </template>

    <template #body>
      <UContainer class="py-6">
        <UChatMessages :messages="messages" :status="chatStatus">
          <template #content="{ message }: { message: WebChatMessage }">
            <div v-if="isThinkingMessage(message)" class="flex items-center gap-2 text-sm text-muted">
              <UIcon name="i-lucide-loader-circle" class="size-4 animate-spin" />
              <span>Thinking…</span>
            </div>

            <template v-for="(part, index) in message.parts" :key="`${message.id}-${part.type}-${index}`">
              <UChatReasoning v-if="part.type === 'reasoning'" :text="partText(part)">
                <Comark :markdown="partText(part)" :plugins="[highlight()]" class="*:first:mt-0 *:last:mb-0" />
              </UChatReasoning>

              <UChatTool v-else-if="part.type === 'tool'" :text="part.name || 'Tool call'" />

              <template v-else-if="part.type === 'text'">
                <Comark
                  v-if="message.role === 'assistant'"
                  :markdown="partText(part)"
                  :plugins="[highlight()]"
                  class="*:first:mt-0 *:last:mb-0"
                />
                <p v-else class="whitespace-pre-wrap">
                  {{ partText(part) }}
                </p>
              </template>
            </template>
          </template>
        </UChatMessages>
        <div ref="bottomRef" class="h-px" aria-hidden="true" />
      </UContainer>
    </template>

    <template #footer>
      <UContainer class="pb-4 sm:pb-6">
        <UChatPrompt v-model="input" :error="error" @submit="onSubmit">
          <UChatPromptSubmit :status="chatStatus" @stop="runStream.stop" />
        </UChatPrompt>
      </UContainer>
    </template>
  </UDashboardPanel>
</template>
