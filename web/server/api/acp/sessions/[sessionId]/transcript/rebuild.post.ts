import type { LoadSessionRequest } from '@agentclientprotocol/sdk'
import { createError, defineEventHandler, getRouterParam, getQuery } from 'h3'
import { useRuntimeConfig } from '#imports'
import { rebuildAcpSessionProjectionFromLoad } from '../../../../../acp/sessionLoadReplay'

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

  const { transcript, events } = await rebuildAcpSessionProjectionFromLoad(config, params)
  return {
    sessionId,
    rebuilt: true,
    events,
    transcript
  }
})
