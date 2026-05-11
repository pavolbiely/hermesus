import type { ListSessionsRequest } from '@agentclientprotocol/sdk'
import { defineEventHandler, getQuery } from 'h3'
import { useRuntimeConfig } from '#imports'
import { getAcpBridge } from '../../../acp/bridge'
import { listAcpSessionMetadata } from '../../../app/acpSessionMetadata'

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig()
  const query = getQuery(event)
  const cursor = typeof query.cursor === 'string' ? query.cursor : undefined
  const cwd = typeof query.cwd === 'string' ? query.cwd : undefined

  const params: ListSessionsRequest = {
    ...(cursor ? { cursor } : {}),
    ...(cwd ? { cwd } : {})
  }

  const [response, metadataBySessionId] = await Promise.all([
    getAcpBridge().listSessions(config, params),
    listAcpSessionMetadata(config)
  ])

  return {
    ...response,
    sessions: response.sessions.map(session => ({
      ...session,
      appMetadata: metadataBySessionId[session.sessionId]
    }))
  }
})
