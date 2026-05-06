import type { ActiveRunSummary } from '~/types/web-chat'

type RecoverActiveRunOptions = {
  sessionId: string
  activeRun?: ActiveRunSummary | null
  hasConnectedRun: (runId: string) => boolean
  connectRun: (runId: string, sessionId: string) => void
}

type ReconcileActiveRunSnapshotOptions = RecoverActiveRunOptions & {
  isRunning: (sessionId: string) => boolean
  clearSessionRun: (sessionId: string) => void
}

const terminalRunStatuses = new Set(['completed', 'stopped', 'failed', 'interrupted'])

export function isLiveActiveRun(activeRun?: ActiveRunSummary | null) {
  return Boolean(activeRun && !terminalRunStatuses.has(activeRun.status))
}

export function recoverActiveRun(options: RecoverActiveRunOptions) {
  const { activeRun, sessionId, hasConnectedRun, connectRun } = options
  if (activeRun === undefined || activeRun === null) return
  if (activeRun.sessionId !== sessionId) return
  if (!isLiveActiveRun(activeRun)) return
  if (hasConnectedRun(activeRun.runId)) return

  connectRun(activeRun.runId, sessionId)
}

export function reconcileActiveRunSnapshot(options: ReconcileActiveRunSnapshotOptions) {
  const { activeRun, sessionId, isRunning, clearSessionRun } = options
  recoverActiveRun(options)

  if (activeRun !== null) return
  if (!isRunning(sessionId)) return

  clearSessionRun(sessionId)
}
