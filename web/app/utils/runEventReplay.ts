export type RunEventReplayHandlers = Record<string, ((payload: never) => void) | undefined>

type ReplayEvent = {
  handler: string
  payload: unknown
}

export function createRunEventReplay() {
  const events: ReplayEvent[] = []

  function record(handler: string, payload: unknown) {
    events.push({ handler, payload })
  }

  function replay(handlers: RunEventReplayHandlers) {
    for (const event of events) {
      const handler = handlers[event.handler]
      if (handler) handler(event.payload as never)
    }
  }

  return { record, replay }
}
