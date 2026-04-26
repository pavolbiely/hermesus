import type { WebChatMessage } from '~/types/web-chat'

type RunStreamHandlers = {
  onDelta?: (content: string) => void
  onCompleted?: (content?: string) => void
  onError?: (error: Error) => void
  onFinished?: () => void
}

function hermesToken() {
  if (import.meta.server) return undefined
  return window.__HERMES_SESSION_TOKEN__
}

function eventSourceUrl(runId: string) {
  const token = hermesToken()
  const url = new URL(`/api/web-chat/runs/${runId}/events`, window.location.origin)
  if (token) url.searchParams.set('session_token', token)
  return url.toString()
}

export function createLocalMessage(role: WebChatMessage['role'], text: string): WebChatMessage {
  return {
    id: crypto.randomUUID(),
    role,
    createdAt: new Date().toISOString(),
    parts: text ? [{ type: 'text', text }] : []
  }
}

export function useHermesRunStream() {
  const currentRunId = ref<string | null>(null)
  const status = ref<'ready' | 'submitted' | 'streaming' | 'error'>('ready')
  const error = ref<Error | undefined>()
  let source: EventSource | null = null

  function close() {
    source?.close()
    source = null
  }

  async function stop() {
    if (!currentRunId.value) return
    await $fetch(`/api/web-chat/runs/${currentRunId.value}/stop`, {
      method: 'POST',
      headers: hermesToken() ? { 'X-Hermes-Session-Token': hermesToken()! } : undefined
    })
    close()
    status.value = 'ready'
    currentRunId.value = null
  }

  function connect(runId: string, handlers: RunStreamHandlers = {}) {
    close()
    currentRunId.value = runId
    status.value = 'streaming'
    error.value = undefined

    source = new EventSource(eventSourceUrl(runId))

    source.addEventListener('message.delta', (event) => {
      const payload = JSON.parse((event as MessageEvent).data)
      handlers.onDelta?.(payload.content || '')
    })

    source.addEventListener('message.completed', (event) => {
      const payload = JSON.parse((event as MessageEvent).data)
      handlers.onCompleted?.(payload.content)
    })

    source.addEventListener('run.completed', () => {
      close()
      status.value = 'ready'
      currentRunId.value = null
      handlers.onFinished?.()
    })

    source.addEventListener('run.stopped', () => {
      close()
      status.value = 'ready'
      currentRunId.value = null
      handlers.onFinished?.()
    })

    source.addEventListener('run.failed', (event) => {
      const payload = JSON.parse((event as MessageEvent).data)
      const nextError = new Error(payload.error || 'Run failed')
      error.value = nextError
      status.value = 'error'
      close()
      handlers.onError?.(nextError)
      handlers.onFinished?.()
    })

    source.onerror = () => {
      const nextError = new Error('Lost connection to Hermes run stream')
      error.value = nextError
      status.value = 'error'
      close()
      handlers.onError?.(nextError)
      handlers.onFinished?.()
    }
  }

  onBeforeUnmount(close)

  return {
    status,
    error,
    currentRunId,
    connect,
    stop
  }
}
