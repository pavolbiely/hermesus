import { createError, defineEventHandler, getRouterParam, readBody } from 'h3'
import { useRuntimeConfig } from '#imports'
import { patchAcpSessionMetadata, type AcpSessionMetadataPatch } from '../../../../app/acpSessionMetadata'

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig()
  const sessionId = getRouterParam(event, 'sessionId')
  if (!sessionId) {
    throw createError({ statusCode: 400, statusMessage: 'Missing sessionId' })
  }

  const body = await readBody<AcpSessionMetadataPatch>(event)
  const metadata = await patchAcpSessionMetadata(config, sessionId, body || {})
  return { sessionId, metadata }
})
