import type { ListSessionsRequest } from '@agentclientprotocol/sdk'
import { defineEventHandler, getQuery } from 'h3'
import { useRuntimeConfig } from '#imports'
import { getAcpBridge } from '../../../acp/bridge'
import { listAcpSessionLineage } from '../../../app/acpSessionLineage'
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

  const bridge = getAcpBridge()
  const [response, lineageBySessionId, metadataBySessionId] = await Promise.all([
    bridge.listSessions(config, params),
    listAcpSessionLineage(config),
    listAcpSessionMetadata(config)
  ])

  return {
    ...response,
    sessions: response.sessions.map(session => ({
      ...session,
      appLineage: lineageBySessionId[session.sessionId],
      appMetadata: metadataBySessionId[session.sessionId],
      appActivePrompt: bridge.activePrompt(session.sessionId)
    }))
  }
})
