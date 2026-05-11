import type { LoadSessionRequest } from '@agentclientprotocol/sdk'
import { createError, defineEventHandler, getRouterParam, getQuery } from 'h3'
import { useRuntimeConfig } from '#imports'
import { getAcpBridge } from '../../../acp/bridge'
import { subscribeAcpSession, type AcpBridgeEvent } from '../../../acp/events'

const replaySettleMs = 50

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig()
  const sessionId = getRouterParam(event, 'sessionId')
  if (!sessionId) {
    throw createError({ statusCode: 400, statusMessage: 'Missing sessionId' })
  }

  const query = getQuery(event)
  const cwd = typeof query.cwd === 'string' ? query.cwd : config.hermesAcpCwd
  const params: LoadSessionRequest = {
    sessionId,
    cwd,
    mcpServers: []
  }

  const events: AcpBridgeEvent[] = []
  const unsubscribe = subscribeAcpSession(sessionId, event => events.push(event))
  try {
    const response = await getAcpBridge().loadSession(config, params)
    await new Promise(resolve => setTimeout(resolve, replaySettleMs))
    return { ...response, events }
  } finally {
    unsubscribe()
  }
})
