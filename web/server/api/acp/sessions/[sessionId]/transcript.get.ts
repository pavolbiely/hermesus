import { createError, defineEventHandler, getRouterParam, getQuery } from 'h3'
import { ensureAcpSessionSequenceAtLeast } from '../../../../acp/events'
import { getAcpTranscriptStore, type AcpTranscriptSnapshot } from '../../../../acp/transcriptStore'

export default defineEventHandler(async (event) => {
  const sessionId = getRouterParam(event, 'sessionId')
  if (!sessionId) {
    throw createError({ statusCode: 400, statusMessage: 'Missing sessionId' })
  }

  const query = getQuery(event)
  const transcript = await getAcpTranscriptStore().get(sessionId)
  ensureAcpSessionSequenceAtLeast(sessionId, transcript?.cursor)
  const pagedTranscript = transcript ? paginateTranscript(transcript, query) : null
  return {
    sessionId,
    found: Boolean(transcript),
    transcript: pagedTranscript?.transcript ?? null,
    hasMore: pagedTranscript?.hasMore ?? false,
    nextBefore: pagedTranscript?.nextBefore ?? null
  }
})

function paginateTranscript(snapshot: AcpTranscriptSnapshot, query: Record<string, unknown>) {
  const limit = positiveInteger(query.limit)
  if (!limit) return { transcript: snapshot, hasMore: false, nextBefore: null }

  const before = Math.min(positiveInteger(query.before) ?? snapshot.messages.length, snapshot.messages.length)
  const start = Math.max(0, before - limit)
  return {
    transcript: {
      ...snapshot,
      messages: snapshot.messages.slice(start, before)
    },
    hasMore: start > 0,
    nextBefore: start > 0 ? start : null
  }
}

function positiveInteger(value: unknown) {
  if (typeof value !== 'string') return null
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}
