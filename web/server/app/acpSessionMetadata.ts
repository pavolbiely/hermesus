import { mkdir, readFile, rename, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'

export type AcpSessionAppMetadata = {
  title?: string | null
  pinned?: boolean
  archived?: boolean
  workspace?: string | null
}

export type AcpSessionMetadataPatch = Partial<AcpSessionAppMetadata>

type MetadataFile = {
  sessions?: Record<string, AcpSessionAppMetadata>
}

type MetadataRuntimeConfig = {
  hermesAcpCwd?: string
}

function metadataPath(config: MetadataRuntimeConfig) {
  const root = config.hermesAcpCwd || process.cwd()
  return join(root, '.hermes', 'web-chat', 'acp-session-metadata.json')
}

function cleanMetadata(value: AcpSessionAppMetadata | undefined): AcpSessionAppMetadata {
  return {
    ...(typeof value?.title === 'string' && value.title.trim() ? { title: value.title.trim() } : {}),
    ...(typeof value?.pinned === 'boolean' ? { pinned: value.pinned } : {}),
    ...(typeof value?.archived === 'boolean' ? { archived: value.archived } : {}),
    ...(value && 'workspace' in value
      ? { workspace: typeof value.workspace === 'string' && value.workspace.trim() ? value.workspace.trim() : null }
      : {})
  }
}

function cleanPatch(patch: AcpSessionMetadataPatch): AcpSessionAppMetadata {
  const next: AcpSessionAppMetadata = {}
  if ('title' in patch) next.title = typeof patch.title === 'string' && patch.title.trim() ? patch.title.trim() : null
  if ('pinned' in patch) next.pinned = Boolean(patch.pinned)
  if ('archived' in patch) next.archived = Boolean(patch.archived)
  if ('workspace' in patch) next.workspace = typeof patch.workspace === 'string' && patch.workspace.trim() ? patch.workspace.trim() : null
  return next
}

async function readMetadataFile(config: MetadataRuntimeConfig): Promise<Record<string, AcpSessionAppMetadata>> {
  try {
    const raw = await readFile(metadataPath(config), 'utf8')
    const parsed = JSON.parse(raw) as MetadataFile
    const sessions = parsed && typeof parsed === 'object' && parsed.sessions && typeof parsed.sessions === 'object'
      ? parsed.sessions
      : {}

    return Object.fromEntries(
      Object.entries(sessions).map(([id, metadata]) => [id, cleanMetadata(metadata)])
    )
  } catch (error: unknown) {
    if (error && typeof error === 'object' && 'code' in error && error.code === 'ENOENT') return {}
    throw error
  }
}

async function writeMetadataFile(config: MetadataRuntimeConfig, sessions: Record<string, AcpSessionAppMetadata>) {
  const filePath = metadataPath(config)
  await mkdir(dirname(filePath), { recursive: true })
  const tmpPath = `${filePath}.${process.pid}.${Date.now()}.tmp`
  await writeFile(tmpPath, `${JSON.stringify({ sessions }, null, 2)}\n`, 'utf8')
  await rename(tmpPath, filePath)
}

export async function listAcpSessionMetadata(config: MetadataRuntimeConfig) {
  return readMetadataFile(config)
}

export async function patchAcpSessionMetadata(config: MetadataRuntimeConfig, sessionId: string, patch: AcpSessionMetadataPatch) {
  const sessions = await readMetadataFile(config)
  const current = cleanMetadata(sessions[sessionId])
  const cleanedPatch = cleanPatch(patch)
  const next = cleanMetadata({ ...current, ...cleanedPatch })

  sessions[sessionId] = next
  await writeMetadataFile(config, sessions)
  return next
}
