import { mkdir, readFile, readdir, rename, rm, writeFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import { join } from 'node:path'
import type { PlanEntry } from '@agentclientprotocol/sdk'
import type {
  AvailableCommand,
  RequestPermissionRequest,
  SessionConfigOption,
  SessionModeState,
  SessionModelState
} from '../../app/types/acp-api'
import type { AcpChatMessage } from '../../shared/acp/types'

export type PersistedPermission = {
  appRequestId: string
  request: RequestPermissionRequest
}

export type PersistedPromptState = {
  status: 'running' | 'completed' | 'failed' | 'cancelled'
  turnId?: string
  messageId?: string
  userMessageId?: string
  error?: string
  startedAt?: string
  completedAt?: string
}

export type AcpTranscriptSnapshot = {
  sessionId: string
  cursor?: number
  updatedAt: string
  messages: AcpChatMessage[]
  pendingPermissions: PersistedPermission[]
  planEntries: PlanEntry[]
  prompt: PersistedPromptState | null
  models: SessionModelState | null
  modes: SessionModeState | null
  configOptions: SessionConfigOption[]
  availableCommands: AvailableCommand[]
}

export type AcpTranscriptStore = {
  get(sessionId: string): Promise<AcpTranscriptSnapshot | null>
  put(snapshot: AcpTranscriptSnapshot): Promise<void>
  delete(sessionId: string): Promise<void>
  clear(): Promise<number>
  listSessionIds(): Promise<string[]>
}

export type FileAcpTranscriptStoreOptions = {
  directory?: string
  rootDir?: string
}

const transcriptFileExtension = '.json'
let defaultStore: AcpTranscriptStore | undefined

export function getAcpTranscriptStore() {
  defaultStore ||= createFileAcpTranscriptStore()
  return defaultStore
}

export function createFileAcpTranscriptStore(options: FileAcpTranscriptStoreOptions = {}): AcpTranscriptStore {
  const directory = options.directory || join(options.rootDir || defaultRuntimeRoot(), '.runtime', 'acp-transcripts')

  return {
    async get(sessionId) {
      try {
        const content = await readFile(filePath(directory, sessionId), 'utf8')
        return parseSnapshot(content, sessionId)
      } catch (error) {
        if (isNotFound(error)) return null
        throw error
      }
    },

    async put(snapshot) {
      const validSnapshot = normalizeSnapshot(snapshot)
      await mkdir(directory, { recursive: true })
      const path = filePath(directory, validSnapshot.sessionId)
      const temporaryPath = `${path}.${process.pid}.${randomUUID()}.tmp`
      try {
        await writeFile(temporaryPath, `${JSON.stringify(validSnapshot, null, 2)}\n`, 'utf8')
        await rename(temporaryPath, path)
      } catch (error) {
        await rm(temporaryPath, { force: true })
        throw error
      }
    },

    async delete(sessionId) {
      await rm(filePath(directory, sessionId), { force: true })
    },

    async clear() {
      const sessionIds = await listSessionIds(directory)
      await Promise.all(sessionIds.map(sessionId => rm(filePath(directory, sessionId), { force: true })))
      return sessionIds.length
    },

    async listSessionIds() {
      return await listSessionIds(directory)
    }
  }
}

export function encodeSessionId(sessionId: string) {
  return Buffer.from(sessionId, 'utf8').toString('base64url')
}

export function decodeSessionId(encoded: string) {
  try {
    return Buffer.from(encoded, 'base64url').toString('utf8')
  } catch {
    return null
  }
}

function filePath(directory: string, sessionId: string) {
  if (!sessionId.trim()) throw new Error('ACP transcript session id is required')
  return join(directory, `${encodeSessionId(sessionId)}${transcriptFileExtension}`)
}

async function listSessionIds(directory: string) {
  try {
    const entries = await readdir(directory, { withFileTypes: true })
    return entries
      .filter(entry => entry.isFile() && entry.name.endsWith(transcriptFileExtension))
      .map(entry => decodeSessionId(entry.name.slice(0, -transcriptFileExtension.length)))
      .filter((sessionId): sessionId is string => Boolean(sessionId))
      .sort()
  } catch (error) {
    if (isNotFound(error)) return []
    throw error
  }
}

function defaultRuntimeRoot() {
  return process.cwd().endsWith('/web') ? process.cwd().slice(0, -4) : process.cwd()
}

function parseSnapshot(content: string, expectedSessionId: string) {
  let parsed: unknown
  try {
    parsed = JSON.parse(content) as unknown
  } catch {
    return null
  }
  if (!isSnapshotLike(parsed) || parsed.sessionId !== expectedSessionId) return null
  return normalizeSnapshot(parsed)
}

function normalizeSnapshot(snapshot: AcpTranscriptSnapshot): AcpTranscriptSnapshot {
  return {
    sessionId: snapshot.sessionId,
    cursor: typeof snapshot.cursor === 'number' && Number.isFinite(snapshot.cursor) ? snapshot.cursor : undefined,
    updatedAt: typeof snapshot.updatedAt === 'string' && snapshot.updatedAt ? snapshot.updatedAt : new Date().toISOString(),
    messages: Array.isArray(snapshot.messages) ? snapshot.messages : [],
    pendingPermissions: Array.isArray(snapshot.pendingPermissions) ? snapshot.pendingPermissions : [],
    planEntries: Array.isArray(snapshot.planEntries) ? snapshot.planEntries : [],
    prompt: isPromptStateLike(snapshot.prompt) ? snapshot.prompt : null,
    models: snapshot.models ?? null,
    modes: snapshot.modes ?? null,
    configOptions: Array.isArray(snapshot.configOptions) ? snapshot.configOptions : [],
    availableCommands: Array.isArray(snapshot.availableCommands) ? snapshot.availableCommands : []
  }
}

function isSnapshotLike(value: unknown): value is AcpTranscriptSnapshot {
  if (!value || typeof value !== 'object') return false
  const record = value as Record<string, unknown>
  return typeof record.sessionId === 'string' && Array.isArray(record.messages)
}

function isPromptStateLike(value: unknown): value is PersistedPromptState {
  if (!value || typeof value !== 'object') return false
  const status = (value as Record<string, unknown>).status
  return status === 'running' || status === 'completed' || status === 'failed' || status === 'cancelled'
}

function isNotFound(error: unknown) {
  return Boolean(error && typeof error === 'object' && 'code' in error && error.code === 'ENOENT')
}
