import type { SetSessionConfigOptionRequest } from '@agentclientprotocol/sdk'
import { createError, defineEventHandler, getRouterParam, readBody } from 'h3'
import { useRuntimeConfig } from '#imports'
import { getAcpBridge } from '../../../../../acp/bridge'

type SetConfigOptionBody = {
  type?: unknown
  value?: unknown
}

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig()
  const sessionId = getRouterParam(event, 'sessionId')
  const configId = getRouterParam(event, 'configId')
  if (!sessionId) {
    throw createError({ statusCode: 400, statusMessage: 'Missing sessionId' })
  }
  if (!configId) {
    throw createError({ statusCode: 400, statusMessage: 'Missing configId' })
  }

  const body = await readBody<SetConfigOptionBody>(event).catch((): SetConfigOptionBody => ({}))
  const params = buildSetConfigOptionRequest(sessionId, configId, body)
  return getAcpBridge().setSessionConfigOption(config, params)
})

function buildSetConfigOptionRequest(sessionId: string, configId: string, body: SetConfigOptionBody): SetSessionConfigOptionRequest {
  if (body.type === 'boolean') {
    if (typeof body.value !== 'boolean') {
      throw createError({ statusCode: 400, statusMessage: 'Boolean config option value must be boolean' })
    }
    return { sessionId, configId, type: 'boolean', value: body.value }
  }

  if (typeof body.value !== 'string' || !body.value.trim()) {
    throw createError({ statusCode: 400, statusMessage: 'Config option value must be a non-empty string' })
  }

  return { sessionId, configId, value: body.value.trim() }
}
