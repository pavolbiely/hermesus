import type { SetSessionModelRequest } from '@agentclientprotocol/sdk'
import { createError, defineEventHandler, getRouterParam, readBody } from 'h3'
import { useRuntimeConfig } from '#imports'
import { getAcpBridge } from '../../../../acp/bridge'

type SetModelBody = {
  modelId?: unknown
}

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig()
  const sessionId = getRouterParam(event, 'sessionId')
  if (!sessionId) {
    throw createError({ statusCode: 400, statusMessage: 'Missing sessionId' })
  }

  const body = await readBody<SetModelBody>(event).catch((): SetModelBody => ({}))
  const modelId = typeof body.modelId === 'string' ? body.modelId.trim() : ''
  if (!modelId) {
    throw createError({ statusCode: 400, statusMessage: 'Missing modelId' })
  }

  const params: SetSessionModelRequest = { sessionId, modelId }
  return getAcpBridge().setSessionModel(config, params)
})
