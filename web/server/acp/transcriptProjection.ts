import { applyAcpChatEvent } from '../../shared/acp/eventNormalization'
import { normalizeAcpBridgeEvent } from '../../shared/acp/bridgeEventNormalization'
import { isAcpPlanUpdate, normalizeAcpPlanEntries } from '../../shared/acp/planNormalization'
import type { AcpBridgeEvent, AcpTranscriptState } from '../../shared/acp/types'
import type { AcpTranscriptSnapshot, AcpTranscriptStore } from './transcriptStore'
import { getAcpTranscriptStore } from './transcriptStore'
import type { LoadSessionResponse } from '@agentclientprotocol/sdk'

const projectionQueues = new Map<string, Promise<void>>()

export type AcpProjectionRebuildOptions = Pick<LoadSessionResponse, 'models' | 'modes' | 'configOptions'>

export function recordAcpProjectionEvent(event: AcpBridgeEvent, store = getAcpTranscriptStore()) {
  return queueProjectionUpdate(event.sessionId, () => updateProjectionFromEvent(event, store))
}

export function rebuildAcpProjection(
  sessionId: string,
  events: AcpBridgeEvent[],
  options: AcpProjectionRebuildOptions = {},
  store = getAcpTranscriptStore()
) {
  return queueProjectionUpdate(sessionId, async () => {
    let snapshot = createEmptySnapshot(sessionId)
    snapshot = {
      ...snapshot,
      models: options.models ?? null,
      modes: options.modes ?? null,
      configOptions: options.configOptions ?? []
    }
    for (const event of events) snapshot = applyAcpProjectionEvent(snapshot, event)
    await store.put(snapshot)
  })
}

function queueProjectionUpdate(sessionId: string, update: () => Promise<void>) {
  const previous = projectionQueues.get(sessionId) ?? Promise.resolve()
  const next = previous
    .catch(() => undefined)
    .then(update)
    .catch((error: unknown) => {
      console.warn('Failed to persist ACP transcript projection', error)
    })
    .finally(() => {
      if (projectionQueues.get(sessionId) === next) projectionQueues.delete(sessionId)
    })

  projectionQueues.set(sessionId, next)
  return next
}

export async function updateProjectionFromEvent(event: AcpBridgeEvent, store: AcpTranscriptStore) {
  const current = await store.get(event.sessionId)
  const next = applyAcpProjectionEvent(current ?? createEmptySnapshot(event.sessionId), event)
  await store.put(next)
}

export function applyAcpProjectionEvent(snapshot: AcpTranscriptSnapshot, event: AcpBridgeEvent): AcpTranscriptSnapshot {
  let state = snapshotToTranscriptState(snapshot)
  for (const chatEvent of normalizeAcpBridgeEvent(event)) {
    state = applyAcpChatEvent(state, chatEvent)
  }

  return applyProjectionMetadata({
    ...snapshot,
    cursor: state.cursor,
    messages: state.messages,
    updatedAt: new Date().toISOString()
  }, event)
}

export function createEmptySnapshot(sessionId: string): AcpTranscriptSnapshot {
  return {
    sessionId,
    updatedAt: new Date().toISOString(),
    messages: [],
    pendingPermissions: [],
    planEntries: [],
    prompt: null,
    models: null,
    modes: null,
    configOptions: [],
    availableCommands: []
  }
}

function snapshotToTranscriptState(snapshot: AcpTranscriptSnapshot): AcpTranscriptState {
  return {
    messages: snapshot.messages,
    cursor: snapshot.cursor,
    seenEventIds: new Set()
  }
}

function applyProjectionMetadata(snapshot: AcpTranscriptSnapshot, event: AcpBridgeEvent): AcpTranscriptSnapshot {
  if (event.type === 'prompt.started') {
    return {
      ...snapshot,
      prompt: {
        status: 'running',
        turnId: event.turnId,
        messageId: event.messageId,
        startedAt: new Date().toISOString()
      }
    }
  }

  if (event.type === 'prompt.completed') {
    if (snapshot.prompt?.status === 'cancelled' && snapshot.prompt.turnId === event.turnId) return snapshot
    return {
      ...snapshot,
      prompt: {
        status: 'completed',
        turnId: event.turnId,
        messageId: event.messageId,
        userMessageId: event.userMessageId,
        completedAt: event.completedAt ?? new Date().toISOString()
      }
    }
  }

  if (event.type === 'prompt.failed') {
    if (snapshot.prompt?.status === 'cancelled' && snapshot.prompt.turnId === event.turnId) return snapshot
    return {
      ...snapshot,
      prompt: {
        status: 'failed',
        turnId: event.turnId,
        messageId: event.messageId,
        error: event.error,
        completedAt: new Date().toISOString()
      }
    }
  }

  if (event.type === 'prompt.cancelled') {
    return {
      ...snapshot,
      prompt: {
        status: 'cancelled',
        turnId: event.turnId ?? (snapshot.prompt?.status === 'running' ? snapshot.prompt.turnId : undefined),
        messageId: event.messageId ?? (snapshot.prompt?.status === 'running' ? snapshot.prompt.messageId : undefined),
        completedAt: new Date().toISOString()
      }
    }
  }

  if (event.type === 'permission.requested') {
    return {
      ...snapshot,
      pendingPermissions: [
        ...snapshot.pendingPermissions.filter(permission => permission.appRequestId !== event.appRequestId),
        { appRequestId: event.appRequestId, request: event.request }
      ]
    }
  }

  if (event.type === 'permission.resolved') {
    return {
      ...snapshot,
      pendingPermissions: snapshot.pendingPermissions.filter(permission => permission.appRequestId !== event.appRequestId)
    }
  }

  if (event.type !== 'session.update') return snapshot

  const update = event.notification.update
  if (update.sessionUpdate === 'current_mode_update' && snapshot.modes) {
    return {
      ...snapshot,
      modes: { ...snapshot.modes, currentModeId: update.currentModeId }
    }
  }

  if (update.sessionUpdate === 'config_option_update') {
    return { ...snapshot, configOptions: Array.isArray(update.configOptions) ? update.configOptions : [] }
  }

  if (update.sessionUpdate === 'available_commands_update') {
    return { ...snapshot, availableCommands: Array.isArray(update.availableCommands) ? update.availableCommands : [] }
  }

  if (isAcpPlanUpdate(update)) {
    return { ...snapshot, planEntries: normalizeAcpPlanEntries(update.entries) }
  }

  return snapshot
}
