import type { LoadSessionRequest } from '@agentclientprotocol/sdk'
import { getAcpBridge } from './bridge'
import { subscribeAcpSession, type AcpBridgeEvent } from './events'
import { rebuildAcpProjection } from './transcriptProjection'
import { getAcpTranscriptStore } from './transcriptStore'
import { reasoningEventsFromSessionFile } from './sessionReasoning'
import { listAcpTurnMetadata } from './turnMetadata'

const replaySettleMs = 50

type BridgeRuntimeConfig = {
  hermesAcpCwd?: string
}

export async function loadAcpSessionWithReplay(config: BridgeRuntimeConfig, params: LoadSessionRequest) {
  const sessionId = params.sessionId
  const events: AcpBridgeEvent[] = []
  const unsubscribe = subscribeAcpSession(sessionId, event => events.push(event))
  try {
    const response = await getAcpBridge().loadSession(config, params)
    await new Promise(resolve => setTimeout(resolve, replaySettleMs))
    events.push(...await replaySupplementEvents(config, sessionId))
    return { response, events }
  } finally {
    unsubscribe()
  }
}

export async function rebuildAcpSessionProjectionFromLoad(config: BridgeRuntimeConfig, params: LoadSessionRequest) {
  const { response, events } = await loadAcpSessionWithReplay(config, params)
  await rebuildAcpProjection(params.sessionId, events, {
    models: response.models,
    modes: response.modes,
    configOptions: response.configOptions
  })
  const transcript = await getAcpTranscriptStore().get(params.sessionId)
  return { response, events, transcript }
}

async function replaySupplementEvents(config: BridgeRuntimeConfig, sessionId: string): Promise<AcpBridgeEvent[]> {
  const turnMetadata = await listAcpTurnMetadata(config, sessionId)
  return [
    ...await reasoningEventsFromSessionFile(config, sessionId, turnMetadata),
    ...completionEventsFromTurnMetadata(sessionId, turnMetadata)
  ]
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
