import { createError, defineEventHandler, getRouterParam, getQuery } from 'h3'
import { subscribeAcpSession, replayAcpSession, type AcpBridgeEvent } from '../../../../acp/events'

function writeEvent(res: NodeJS.WritableStream, event: AcpBridgeEvent) {
  res.write(`event: ${event.type}\n`)
  res.write(`data: ${JSON.stringify(event)}\n\n`)
}

export default defineEventHandler((event) => {
  const sessionId = getRouterParam(event, 'sessionId')
  if (!sessionId) {
    throw createError({ statusCode: 400, statusMessage: 'Missing sessionId' })
  }

  const { req, res } = event.node
  const query = getQuery(event)
  const afterQuery = typeof query.after === 'string' ? Number(query.after) : undefined
  const after = afterQuery !== undefined && Number.isFinite(afterQuery) ? afterQuery : undefined
  const replay = query.replay !== 'false'
  res.writeHead(200, {
    'cache-control': 'no-cache, no-transform',
    'connection': 'keep-alive',
    'content-type': 'text/event-stream',
    'x-accel-buffering': 'no'
  })
  res.write(': connected\n\n')

  const unsubscribe = subscribeAcpSession(sessionId, (acpEvent) => writeEvent(res, acpEvent))
  if (replay) {
    replayAcpSession(sessionId)
      .filter(acpEvent => after === undefined || acpEvent.sequence === undefined || acpEvent.sequence > after)
      .forEach((acpEvent) => writeEvent(res, acpEvent))
  }

  req.on('close', () => {
    unsubscribe()
    res.end()
  })
})
