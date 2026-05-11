import type { Usage } from '@agentclientprotocol/sdk'
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import type { AcpAttachmentPart } from '../../shared/acp/types'

export type AcpTurnMetadata = {
  turnId: string
  userMessageId: string
  completedAt: string
  usage?: Usage | null
  promptText?: string
  attachments?: AcpAttachmentPart[]
}

type MetadataFile = {
  sessions?: Record<string, AcpTurnMetadata[]>
}

type MetadataRuntimeConfig = {
  hermesAcpCwd?: string
}

function metadataPath(config: MetadataRuntimeConfig) {
  const root = config.hermesAcpCwd || process.cwd()
  return join(root, '.hermes', 'web-chat', 'acp-turn-metadata.json')
}

function cleanTurnMetadata(value: Partial<AcpTurnMetadata> | undefined): AcpTurnMetadata | null {
  if (!value || typeof value.turnId !== 'string' || !value.turnId) return null
  if (typeof value.userMessageId !== 'string' || !value.userMessageId) return null
  if (typeof value.completedAt !== 'string' || !value.completedAt) return null

  return {
    turnId: value.turnId,
    userMessageId: value.userMessageId,
    completedAt: value.completedAt,
    usage: value.usage ?? null,
    promptText: typeof value.promptText === 'string' ? value.promptText : undefined,
    attachments: cleanAttachments(value.attachments)
  }
}

function cleanAttachments(value: unknown): AcpAttachmentPart[] | undefined {
  if (!Array.isArray(value)) return undefined
  const attachments = value.flatMap((item): AcpAttachmentPart[] => {
    if (!item || typeof item !== 'object') return []
    const record = item as Record<string, unknown>
    if (record.type !== 'attachment' || typeof record.name !== 'string' || typeof record.mediaType !== 'string') return []
    return [{
      type: 'attachment',
      id: typeof record.id === 'string' ? record.id : undefined,
      name: record.name,
      mediaType: record.mediaType,
      size: typeof record.size === 'number' ? record.size : undefined,
      data: typeof record.data === 'string' ? record.data : undefined
    }]
  })
  return attachments.length ? attachments : undefined
}

async function readMetadataFile(config: MetadataRuntimeConfig): Promise<Record<string, AcpTurnMetadata[]>> {
  try {
    const raw = await readFile(metadataPath(config), 'utf8')
    const parsed = JSON.parse(raw) as MetadataFile
    const sessions = parsed && typeof parsed === 'object' && parsed.sessions && typeof parsed.sessions === 'object'
      ? parsed.sessions
      : {}

    return Object.fromEntries(
      Object.entries(sessions).map(([sessionId, turns]) => [
        sessionId,
        Array.isArray(turns) ? turns.flatMap(turn => cleanTurnMetadata(turn) ?? []) : []
      ])
    )
  } catch (error: unknown) {
    if (error && typeof error === 'object' && 'code' in error && error.code === 'ENOENT') return {}
    throw error
  }
}

async function writeMetadataFile(config: MetadataRuntimeConfig, sessions: Record<string, AcpTurnMetadata[]>) {
  const filePath = metadataPath(config)
  await mkdir(dirname(filePath), { recursive: true })
  const tmpPath = `${filePath}.${process.pid}.${Date.now()}.tmp`
  await writeFile(tmpPath, `${JSON.stringify({ sessions }, null, 2)}\n`, 'utf8')
  await rename(tmpPath, filePath)
}

export async function listAcpTurnMetadata(config: MetadataRuntimeConfig, sessionId: string) {
  const sessions = await readMetadataFile(config)
  return sessions[sessionId] ?? []
}

export async function recordAcpTurnMetadata(config: MetadataRuntimeConfig, sessionId: string, metadata: AcpTurnMetadata) {
  const sessions = await readMetadataFile(config)
  const turns = sessions[sessionId] ?? []
  const next = turns.filter(turn => turn.turnId !== metadata.turnId && turn.userMessageId !== metadata.userMessageId)
  next.push(metadata)
  sessions[sessionId] = next
  await writeMetadataFile(config, sessions)
}
