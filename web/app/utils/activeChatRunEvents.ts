import type { AgentStatusEvent, InteractivePrompt, WebChatTaskPlan } from '~/types/web-chat'

export type RunEventPayload = Record<string, unknown>

export function parseRunEventPayload(event: Event): RunEventPayload {
  return JSON.parse((event as MessageEvent).data)
}

export function promptFromRunPayload(payload: RunEventPayload) {
  const prompt = payload.prompt
  return prompt && typeof prompt === 'object' ? prompt as InteractivePrompt : null
}

export function statusFromRunPayload(payload: RunEventPayload): AgentStatusEvent | null {
  if (typeof payload.message !== 'string' || !payload.message) return null
  return {
    kind: typeof payload.kind === 'string' ? payload.kind : 'lifecycle',
    message: payload.message,
    createdAt: typeof payload.createdAt === 'string' ? payload.createdAt : null
  }
}

export function taskPlanFromRunPayload(payload: RunEventPayload): WebChatTaskPlan | null {
  const taskPlan = payload.taskPlan
  if (!taskPlan || typeof taskPlan !== 'object') return null

  const items = (taskPlan as { items?: unknown }).items
  if (!Array.isArray(items)) return null

  return taskPlan as WebChatTaskPlan
}

export function numericMetric(metrics: Record<string, unknown>, key: string) {
  const value = metrics[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function eventTimestamp() {
  return new Date().toISOString()
}
