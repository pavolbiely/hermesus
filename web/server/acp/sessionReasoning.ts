import { readFile, readdir } from 'node:fs/promises'
import { join } from 'node:path'
import type { SessionNotification } from '@agentclientprotocol/sdk'
import type { AcpBridgeEvent } from '../../shared/acp/types'
import type { AcpTurnMetadata } from './turnMetadata'

type SessionFile = {
  session_id?: string
  messages?: SessionMessage[]
}

type SessionMessage = {
  role?: string
  reasoning?: unknown
  codex_reasoning_items?: unknown
}

type ReasoningRuntimeConfig = {
  hermesHome?: string
  hermesAcpCwd?: string
}

export async function reasoningEventsFromSessionFile(
  config: ReasoningRuntimeConfig,
  sessionId: string,
  turns: AcpTurnMetadata[]
): Promise<AcpBridgeEvent[]> {
  if (!turns.length) return []

  const session = await readHermesSession(config, sessionId)
  if (!session?.messages?.length) return []

  const reasoningByTurn = extractReasoningByTurn(session.messages, turns.length)
  return turns.flatMap((turn, index) => {
    const text = reasoningByTurn[index]?.trim()
    if (!text) return []
    return [reasoningEvent(sessionId, turn.turnId, text, `stored:${index}`)]
  })
}

export async function latestReasoningEventFromSessionFile(
  config: ReasoningRuntimeConfig,
  sessionId: string,
  turnId: string
): Promise<AcpBridgeEvent | null> {
  const session = await readHermesSession(config, sessionId)
  if (!session?.messages?.length) return null

  const text = extractLatestTurnReasoning(session.messages).trim()
  if (!text) return null
  return reasoningEvent(sessionId, turnId, text, 'latest')
}

function reasoningEvent(sessionId: string, turnId: string, text: string, idSuffix: string): AcpBridgeEvent {
  return {
    type: 'session.update',
    sessionId,
    turnId,
    notification: {
      sessionId,
      update: {
        sessionUpdate: 'agent_thought_chunk',
        content: { type: 'text', text },
        messageId: `reasoning-${turnId}-${idSuffix}`
      }
    } as SessionNotification
  }
}

async function readHermesSession(config: ReasoningRuntimeConfig, sessionId: string): Promise<SessionFile | null> {
  const sessionsDir = hermesSessionsDir(config)
  if (!sessionsDir) return null

  const directPath = join(sessionsDir, `session_${sessionId}.json`)
  const direct = await readSessionFile(directPath)
  if (direct) return direct

  try {
    const entries = await readdir(sessionsDir, { withFileTypes: true })
    for (const entry of entries) {
      if (!entry.isFile() || !entry.name.endsWith('.json')) continue
      const session = await readSessionFile(join(sessionsDir, entry.name))
      if (session?.session_id === sessionId) return session
    }
  } catch {
    return null
  }

  return null
}

async function readSessionFile(path: string): Promise<SessionFile | null> {
  try {
    const parsed = JSON.parse(await readFile(path, 'utf8')) as SessionFile
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch {
    return null
  }
}

function hermesSessionsDir(config: ReasoningRuntimeConfig) {
  const hermesHome = config.hermesHome || process.env.HERMES_HOME
  return hermesHome ? join(hermesHome, 'sessions') : null
}

function extractReasoningByTurn(messages: SessionMessage[], turnCount: number) {
  const turns: string[] = []
  let current: string[] | null = null

  for (const message of messages) {
    if (message.role === 'user') {
      if (current) turns.push(joinReasoning(current))
      current = []
      continue
    }

    if (message.role !== 'assistant' || !current) continue
    const text = reasoningText(message)
    if (text) current.push(text)
  }

  if (current) turns.push(joinReasoning(current))
  return turns.slice(-turnCount)
}

function extractLatestTurnReasoning(messages: SessionMessage[]) {
  const latest: string[] = []

  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (!message) continue
    if (message.role === 'user') break
    if (message.role !== 'assistant') continue

    const text = reasoningText(message)
    if (text) latest.unshift(text)
  }

  return joinReasoning(latest)
}

function reasoningText(message: SessionMessage) {
  if (typeof message.reasoning === 'string' && message.reasoning.trim()) return message.reasoning
  return codexReasoningSummary(message.codex_reasoning_items)
}

function codexReasoningSummary(value: unknown) {
  if (!Array.isArray(value)) return ''

  return value.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const summary = (item as { summary?: unknown }).summary
    if (!Array.isArray(summary)) return []
    return summary.flatMap((entry) => {
      if (!entry || typeof entry !== 'object') return []
      const text = (entry as { text?: unknown }).text
      return typeof text === 'string' && text.trim() ? [text] : []
    })
  }).join('\n\n')
}

function joinReasoning(parts: string[]) {
  return parts.map(part => part.trim()).filter(Boolean).join('\n\n')
}
