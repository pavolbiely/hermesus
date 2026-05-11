import type { RequestPermissionRequest, RequestPermissionResponse } from '@agentclientprotocol/sdk'
import { publishAcpEvent } from './events'

type PendingPermissionRequest = {
  request: RequestPermissionRequest
  resolve: (response: RequestPermissionResponse) => void
}

const pendingPermissions = new Map<string, PendingPermissionRequest>()

export function requestAcpPermission(request: RequestPermissionRequest): Promise<RequestPermissionResponse> {
  const appRequestId = crypto.randomUUID()

  publishAcpEvent({
    type: 'permission.requested',
    sessionId: request.sessionId,
    appRequestId,
    request
  })

  return new Promise((resolve) => {
    pendingPermissions.set(appRequestId, { request, resolve })
  })
}

export function resolveAcpPermission(appRequestId: string, optionId?: string): { sessionId: string, response: RequestPermissionResponse } | null {
  const pending = pendingPermissions.get(appRequestId)
  if (!pending) return null
  if (optionId && !pending.request.options.some(option => option.optionId === optionId)) return null

  pendingPermissions.delete(appRequestId)
  const response: RequestPermissionResponse = optionId
    ? { outcome: { outcome: 'selected', optionId } }
    : { outcome: { outcome: 'cancelled' } }

  pending.resolve(response)
  publishAcpEvent({
    type: 'permission.resolved',
    sessionId: pending.request.sessionId,
    appRequestId,
    response
  })

  return { sessionId: pending.request.sessionId, response }
}
