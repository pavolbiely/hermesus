import { createError, defineEventHandler, getRouterParam, readBody } from 'h3'
import { resolveAcpPermission } from '../../../acp/permissions'

type PermissionDecisionBody = {
  optionId?: string
  cancelled?: boolean
}

export default defineEventHandler(async (event) => {
  const appRequestId = getRouterParam(event, 'appRequestId')
  if (!appRequestId) {
    throw createError({ statusCode: 400, statusMessage: 'Missing appRequestId' })
  }

  const body = await readBody<PermissionDecisionBody>(event)
  const optionId = body?.cancelled ? undefined : body?.optionId
  const resolved = resolveAcpPermission(appRequestId, optionId)
  if (!resolved) {
    throw createError({ statusCode: 404, statusMessage: 'Permission request not found' })
  }

  return { appRequestId, sessionId: resolved.sessionId, response: resolved.response }
})
