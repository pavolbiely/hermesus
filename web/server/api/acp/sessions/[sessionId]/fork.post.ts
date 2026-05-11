import type { ForkSessionRequest } from '@agentclientprotocol/sdk'
import { createError, defineEventHandler, getRouterParam, readBody } from 'h3'
import { useRuntimeConfig } from '#imports'
import { getAcpBridge } from '../../../../acp/bridge'

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig()
  const sessionId = getRouterParam(event, 'sessionId')
  if (!sessionId) {
    throw createError({ statusCode: 400, statusMessage: 'Missing sessionId' })
  }

  const body = await readBody<Partial<ForkSessionRequest>>(event)
  const cwd = typeof body?.cwd === 'string' && body.cwd ? body.cwd : config.hermesAcpCwd
  const params: ForkSessionRequest = {
    sessionId,
    cwd,
    mcpServers: [],
    ...(Array.isArray(body?.additionalDirectories) ? { additionalDirectories: body.additionalDirectories } : {})
  }

  return getAcpBridge().forkSession(config, params)
})
