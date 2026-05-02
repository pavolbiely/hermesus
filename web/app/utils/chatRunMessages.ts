import type { WebChatMessage, WebChatTaskPlanItemStatus } from '~/types/web-chat'

export type RunMetrics = Partial<Pick<WebChatMessage,
  | 'tokenCount'
  | 'inputTokens'
  | 'outputTokens'
  | 'cacheReadTokens'
  | 'cacheWriteTokens'
  | 'reasoningTokens'
  | 'contextTokens'
  | 'apiCalls'
  | 'generationDurationMs'
  | 'modelDurationMs'
  | 'toolDurationMs'
  | 'promptWaitDurationMs'
>>

export function inputTokenCount(metrics: RunMetrics) {
  const total = [metrics.inputTokens, metrics.cacheReadTokens, metrics.cacheWriteTokens]
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
    .reduce((sum, value) => sum + value, 0)
  return total > 0 ? total : null
}

export function applyRunMetrics(message: WebChatMessage, metrics: RunMetrics) {
  message.tokenCount = metrics.tokenCount ?? null
  message.inputTokens = metrics.inputTokens ?? null
  message.outputTokens = metrics.outputTokens ?? null
  message.cacheReadTokens = metrics.cacheReadTokens ?? null
  message.cacheWriteTokens = metrics.cacheWriteTokens ?? null
  message.reasoningTokens = metrics.reasoningTokens ?? null
  message.contextTokens = metrics.contextTokens ?? null
  message.apiCalls = metrics.apiCalls ?? null
  message.generationDurationMs = metrics.generationDurationMs ?? null
  message.modelDurationMs = metrics.modelDurationMs ?? null
  message.toolDurationMs = metrics.toolDurationMs ?? null
  message.promptWaitDurationMs = metrics.promptWaitDurationMs ?? null
}

export function finalizeTaskPlansInMessages(messages: WebChatMessage[], finalStatus: Extract<WebChatTaskPlanItemStatus, 'completed' | 'cancelled'>) {
  let changed = false
  const updatedAt = new Date().toISOString()

  for (let messageIndex = messages.length - 1; messageIndex >= 0; messageIndex -= 1) {
    const message = messages[messageIndex]
    if (!message || message.role === 'user') break

    for (const part of message.parts) {
      const taskPlan = part.taskPlan
      if (!taskPlan?.items.length) continue

      let planChanged = false
      const items = taskPlan.items.map((item) => {
        if (item.status !== 'in_progress') return item
        changed = true
        planChanged = true
        return { ...item, status: finalStatus }
      })

      if (planChanged) {
        part.taskPlan = { ...taskPlan, items, updatedAt }
      }
    }
  }

  return changed
}

export function latestTaskPlanFromMessages(messages: WebChatMessage[]) {
  for (let messageIndex = messages.length - 1; messageIndex >= 0; messageIndex -= 1) {
    const message = messages[messageIndex]
    if (!message) continue
    if (message.role === 'user') return null

    for (let partIndex = message.parts.length - 1; partIndex >= 0; partIndex -= 1) {
      const taskPlan = message.parts[partIndex]?.taskPlan
      if (taskPlan?.items.length) return taskPlan
    }
  }
  return null
}
