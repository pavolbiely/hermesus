import type { LoadSessionRequest } from '@agentclientprotocol/sdk'
import { supplementMissingTranscriptEvents } from './sessionReplaySupplement'
import { getAcpBridge } from './bridge'
import { captureAcpSessionReplay, type AcpBridgeEvent } from './events'
import { readHermesSession, type HermesSessionRuntimeConfig } from './sessionFile'
import { reasoningEventsFromSessionFile } from './sessionReasoning'
import { listAcpTurnMetadata } from './turnMetadata'

const replaySettleMs = 50

type BridgeRuntimeConfig = {
  hermesHome?: string
  hermesAcpCwd?: string
}

export async function loadAcpSessionWithReplay(config: BridgeRuntimeConfig, params: LoadSessionRequest) {
  const sessionId = params.sessionId
  const events: AcpBridgeEvent[] = []
  const unsubscribe = captureAcpSessionReplay(sessionId, event => events.push(event))
  try {
    const response = await getAcpBridge().loadSession(config, params)
    await new Promise(resolve => setTimeout(resolve, replaySettleMs))
    const turnMetadata = await listAcpTurnMetadata(config, sessionId)
    applyAttachmentSupplements(events, turnMetadata)
    events.push(...await missingTranscriptEventsFromSessionFile(config, sessionId, events))
    events.push(...await replaySupplementEvents(config, sessionId, turnMetadata))
    return { response, events }
  } finally {
    unsubscribe()
  }
}

async function replaySupplementEvents(config: BridgeRuntimeConfig, sessionId: string, turnMetadata: Awaited<ReturnType<typeof listAcpTurnMetadata>>): Promise<AcpBridgeEvent[]> {
  return [
    ...await reasoningEventsFromSessionFile(config, sessionId, turnMetadata),
    ...completionEventsFromTurnMetadata(sessionId, turnMetadata)
  ]
}

async function missingTranscriptEventsFromSessionFile(config: HermesSessionRuntimeConfig, sessionId: string, replayedEvents: AcpBridgeEvent[]) {
  const session = await readHermesSession(config, sessionId)
  if (!session?.messages?.length) return []
  return supplementMissingTranscriptEvents(sessionId, session.messages, replayedEvents)
}

function applyAttachmentSupplements(events: AcpBridgeEvent[], turnMetadata: Awaited<ReturnType<typeof listAcpTurnMetadata>>) {
  const usedIndexes = new Set<number>()

  for (const metadata of turnMetadata) {
    if (!metadata.attachments?.length || !metadata.promptText) continue
    const index = events.findIndex((event, eventIndex) => {
      if (usedIndexes.has(eventIndex) || event.type !== 'session.update') return false
      const update = event.notification.update as Record<string, unknown>
      return update.sessionUpdate === 'user_message_chunk' && textFromContent(update.content) === metadata.promptText
    })
    if (index === -1) continue

    usedIndexes.add(index)
    events[index] = {
      ...events[index],
      turnId: metadata.turnId,
      messageId: metadata.userMessageId,
      userAttachments: metadata.attachments
    } as AcpBridgeEvent
  }
}

function textFromContent(content: unknown) {
  if (!content || typeof content !== 'object') return ''
  const record = content as Record<string, unknown>
  return typeof record.text === 'string' ? record.text : ''
}

function completionEventsFromTurnMetadata(sessionId: string, turnMetadata: Awaited<ReturnType<typeof listAcpTurnMetadata>>): AcpBridgeEvent[] {
  return turnMetadata.map((metadata): AcpBridgeEvent => ({
    type: 'prompt.completed',
    sessionId,
    turnId: metadata.turnId,
    messageId: metadata.userMessageId,
    userMessageId: metadata.userMessageId,
    completedAt: metadata.completedAt,
    response: {
      stopReason: 'end_turn',
      usage: metadata.usage ?? null,
      userMessageId: metadata.userMessageId
    }
  }))
}
