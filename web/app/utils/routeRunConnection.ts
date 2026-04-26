type ConnectRouteRunOptions = {
  sessionId: string
  queryRun: unknown
  hasConnectedRun: (runId: string) => boolean
  connectRun: (runId: string, sessionId: string) => void
}

export function connectRouteRun(options: ConnectRouteRunOptions) {
  if (typeof options.queryRun !== 'string') return
  if (!options.queryRun || options.hasConnectedRun(options.queryRun)) return
  options.connectRun(options.queryRun, options.sessionId)
}
