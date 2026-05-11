import type { PlanEntry } from '@agentclientprotocol/sdk'

const validPriorities = new Set<PlanEntry['priority']>(['high', 'medium', 'low'])
const validStatuses = new Set<PlanEntry['status']>(['pending', 'in_progress', 'completed'])

export function normalizeAcpPlanEntries(value: unknown): PlanEntry[] {
  if (!Array.isArray(value)) return []

  return value.flatMap((entry) => {
    if (!entry || typeof entry !== 'object') return []

    const record = entry as Record<string, unknown>
    const content = typeof record.content === 'string' ? record.content.trim() : ''
    const status = validStatuses.has(record.status as PlanEntry['status'])
      ? record.status as PlanEntry['status']
      : undefined
    const priority = validPriorities.has(record.priority as PlanEntry['priority'])
      ? record.priority as PlanEntry['priority']
      : 'medium'

    if (!content || !status) return []

    return [{ content, priority, status }]
  })
}

export function isAcpPlanUpdate(update: unknown): update is { sessionUpdate: 'plan', entries: unknown[] } {
  return Boolean(
    update
    && typeof update === 'object'
    && (update as Record<string, unknown>).sessionUpdate === 'plan'
    && Array.isArray((update as Record<string, unknown>).entries)
  )
}
