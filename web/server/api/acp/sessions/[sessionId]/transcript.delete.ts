import { createError, defineEventHandler, getRouterParam } from 'h3'
import { getAcpTranscriptStore } from '../../../../acp/transcriptStore'

export default defineEventHandler(async (event) => {
  const sessionId = getRouterParam(event, 'sessionId')
  if (!sessionId) {
    throw createError({ statusCode: 400, statusMessage: 'Missing sessionId' })
  }

  await getAcpTranscriptStore().delete(sessionId)
  return { sessionId, deleted: true }
})
