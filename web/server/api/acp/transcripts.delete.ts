import { defineEventHandler } from 'h3'
import { getAcpTranscriptStore } from '../../acp/transcriptStore'

export default defineEventHandler(async () => {
  const deleted = await getAcpTranscriptStore().clear()
  return { deleted, cleared: true }
})
