import type { SetSessionModeRequest } from '@agentclientprotocol/sdk'
import { createError, defineEventHandler, getRouterParam, readBody } from 'h3'
import { useRuntimeConfig } from '#imports'
import { getAcpBridge } from '../../../../acp/bridge'

type SetModeBody = {
  modeId?: unknown
}

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig()
  const sessionId = getRouterParam(event, 'sessionId')
  if (!sessionId) {
    throw createError({ statusCode: 400, statusMessage: 'Missing sessionId' })
  }

  const body = await readBody<SetModeBody>(event).catch((): SetModeBody => ({}))
  const modeId = typeof body.modeId === 'string' ? body.modeId.trim() : ''
  if (!modeId) {
    throw createError({ statusCode: 400, statusMessage: 'Missing modeId' })
  }

  const params: SetSessionModeRequest = { sessionId, modeId }
  return getAcpBridge().setSessionMode(config, params)
})
