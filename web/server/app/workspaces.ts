import { createError } from 'h3'
import { mkdir, readFile, rename, stat, writeFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import { dirname, join, resolve } from 'node:path'
import { homedir } from 'node:os'

export type AppWorkspace = {
  id: string
  label: string
  path: string
  active: boolean
}

export type SaveWorkspacePayload = {
  label?: unknown
  path?: unknown
}

type StoredWorkspace = {
  id: string
  label: string
  path: string
}

type WorkspaceSettingsFile = {
  version?: number
  workspaces?: StoredWorkspace[]
}

type WorkspaceRuntimeConfig = {
  hermesAcpCwd?: string
}

function settingsPath(config: WorkspaceRuntimeConfig) {
  const root = config.hermesAcpCwd || process.cwd()
  return join(root, '.hermes', 'web-chat', 'settings.json')
}

function expandHome(path: string) {
  if (path === '~') return homedir()
  if (path.startsWith('~/')) return join(homedir(), path.slice(2))
  return path
}

function portablePath(path: string) {
  const home = homedir()
  return path === home ? '~' : path.startsWith(`${home}/`) ? `~/${path.slice(home.length + 1)}` : path
}

function absolutePath(path: string) {
  return resolve(expandHome(path.trim()))
}

function toAppWorkspace(workspace: StoredWorkspace): AppWorkspace {
  return {
    id: workspace.id,
    label: workspace.label,
    path: absolutePath(workspace.path),
    active: false
  }
}

function cleanStoredWorkspace(value: StoredWorkspace): StoredWorkspace | null {
  if (!value || typeof value !== 'object') return null
  const id = typeof value.id === 'string' ? value.id.trim() : ''
  const label = typeof value.label === 'string' ? value.label.trim() : ''
  const path = typeof value.path === 'string' ? value.path.trim() : ''
  if (!id || !label || !path) return null
  return { id, label, path }
}

async function readSettings(config: WorkspaceRuntimeConfig): Promise<StoredWorkspace[]> {
  try {
    const raw = await readFile(settingsPath(config), 'utf8')
    const parsed = JSON.parse(raw) as WorkspaceSettingsFile
    return Array.isArray(parsed.workspaces)
      ? parsed.workspaces.map(cleanStoredWorkspace).filter((workspace): workspace is StoredWorkspace => Boolean(workspace))
      : []
  } catch (error: unknown) {
    if (error && typeof error === 'object' && 'code' in error && error.code === 'ENOENT') return []
    throw error
  }
}

async function writeSettings(config: WorkspaceRuntimeConfig, workspaces: StoredWorkspace[]) {
  const filePath = settingsPath(config)
  await mkdir(dirname(filePath), { recursive: true })
  const tmpPath = `${filePath}.${process.pid}.${Date.now()}.tmp`
  await writeFile(tmpPath, `${JSON.stringify({ version: 1, workspaces }, null, 2)}\n`, 'utf8')
  await rename(tmpPath, filePath)
}

function httpError(statusCode: number, statusMessage: string) {
  return createError({ statusCode, statusMessage, message: statusMessage, data: { detail: statusMessage } })
}

async function validateDirectory(path: string) {
  try {
    const info = await stat(path)
    if (!info.isDirectory()) throw httpError(400, 'Directory does not exist')
  } catch (error: unknown) {
    if (error && typeof error === 'object' && 'statusCode' in error) throw error
    throw httpError(400, 'Directory does not exist')
  }
}

async function cleanPayload(payload: SaveWorkspacePayload) {
  const label = typeof payload.label === 'string' ? payload.label.trim() : ''
  const rawPath = typeof payload.path === 'string' ? payload.path.trim() : ''
  if (!label) throw httpError(400, 'Workspace label is required')
  if (!rawPath) throw httpError(400, 'Workspace path is required')

  const path = absolutePath(rawPath)
  await validateDirectory(path)
  return { label, path }
}

export async function listWorkspaces(config: WorkspaceRuntimeConfig) {
  const workspaces = await readSettings(config)
  return {
    workspaces: workspaces.map(toAppWorkspace),
    activeWorkspace: null
  }
}

export async function createWorkspace(config: WorkspaceRuntimeConfig, payload: SaveWorkspacePayload) {
  const current = await readSettings(config)
  const next = await cleanPayload(payload)
  if (current.some(workspace => absolutePath(workspace.path) === next.path)) {
    throw httpError(400, 'Workspace path already exists')
  }

  const workspace: StoredWorkspace = {
    id: randomUUID(),
    label: next.label,
    path: portablePath(next.path)
  }
  await writeSettings(config, [...current, workspace])
  return { workspace: toAppWorkspace(workspace) }
}

export async function updateWorkspace(config: WorkspaceRuntimeConfig, workspaceId: string, payload: SaveWorkspacePayload) {
  const current = await readSettings(config)
  const index = current.findIndex(workspace => workspace.id === workspaceId)
  if (index === -1) throw httpError(404, 'Workspace not found')

  const next = await cleanPayload(payload)
  if (current.some(workspace => workspace.id !== workspaceId && absolutePath(workspace.path) === next.path)) {
    throw httpError(400, 'Workspace path already exists')
  }

  const workspace: StoredWorkspace = {
    id: workspaceId,
    label: next.label,
    path: portablePath(next.path)
  }
  const workspaces = [...current]
  workspaces[index] = workspace
  await writeSettings(config, workspaces)
  return { workspace: toAppWorkspace(workspace) }
}

export async function reorderWorkspaces(config: WorkspaceRuntimeConfig, workspaceIds: string[]) {
  if (new Set(workspaceIds).size !== workspaceIds.length) throw httpError(400, 'Workspace IDs must be unique')

  const current = await readSettings(config)
  const byId = new Map(current.map(workspace => [workspace.id, workspace]))
  for (const id of workspaceIds) {
    if (!byId.has(id)) throw httpError(404, 'Workspace not found')
  }

  const requested = new Set(workspaceIds)
  const reordered = [
    ...workspaceIds.map(id => byId.get(id)).filter((workspace): workspace is StoredWorkspace => Boolean(workspace)),
    ...current.filter(workspace => !requested.has(workspace.id))
  ]
  await writeSettings(config, reordered)
  return {
    workspaces: reordered.map(toAppWorkspace),
    activeWorkspace: null
  }
}

export async function deleteWorkspace(config: WorkspaceRuntimeConfig, workspaceId: string) {
  const current = await readSettings(config)
  const next = current.filter(workspace => workspace.id !== workspaceId)
  if (next.length === current.length) throw httpError(404, 'Workspace not found')
  await writeSettings(config, next)
  return { ok: true }
}

export async function suggestWorkspaceDirectories(prefix: string) {
  const value = prefix.trim()
  if (!value) return { suggestions: [] as string[] }

  const expanded = expandHome(value)
  const slashIndex = expanded.lastIndexOf('/')
  const parent = slashIndex <= 0 ? '/' : expanded.slice(0, slashIndex)
  const childPrefix = slashIndex < 0 ? expanded : expanded.slice(slashIndex + 1)

  try {
    const { readdir } = await import('node:fs/promises')
    const entries = await readdir(parent, { withFileTypes: true })
    const suggestions = entries
      .filter(entry => entry.isDirectory() && entry.name.toLowerCase().startsWith(childPrefix.toLowerCase()))
      .map(entry => join(parent, entry.name))
      .sort((a, b) => a.localeCompare(b))
      .slice(0, 300)
    return { suggestions }
  } catch {
    return { suggestions: [] as string[] }
  }
}
