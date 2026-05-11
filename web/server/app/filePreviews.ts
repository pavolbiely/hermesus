import { createError } from 'h3'
import { stat, readFile } from 'node:fs/promises'
import { homedir } from 'node:os'
import { basename, extname, isAbsolute, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { listWorkspaces } from './workspaces'

const execFileAsync = promisify(execFile)

const MAX_FILE_PREVIEW_BYTES = 256 * 1024
const TEXT_EXTENSIONS = new Set([
  '.bash', '.c', '.conf', '.cpp', '.cs', '.css', '.csv', '.dart', '.env', '.go', '.graphql', '.h', '.html', '.ini', '.java', '.js', '.json', '.jsx', '.kt', '.log', '.lua', '.md', '.mjs', '.php', '.plist', '.py', '.rb', '.rs', '.scss', '.sh', '.sql', '.swift', '.toml', '.ts', '.tsx', '.txt', '.vue', '.xml', '.yaml', '.yml', '.zsh'
])

const LANGUAGE_BY_EXTENSION: Record<string, string> = {
  '.bash': 'bash',
  '.c': 'c',
  '.conf': 'ini',
  '.cpp': 'cpp',
  '.cs': 'csharp',
  '.css': 'css',
  '.csv': 'csv',
  '.dart': 'dart',
  '.env': 'dotenv',
  '.go': 'go',
  '.graphql': 'graphql',
  '.h': 'c',
  '.html': 'html',
  '.ini': 'ini',
  '.java': 'java',
  '.js': 'javascript',
  '.json': 'json',
  '.jsx': 'jsx',
  '.kt': 'kotlin',
  '.lua': 'lua',
  '.md': 'markdown',
  '.mjs': 'javascript',
  '.php': 'php',
  '.plist': 'xml',
  '.py': 'python',
  '.rb': 'ruby',
  '.rs': 'rust',
  '.scss': 'scss',
  '.sh': 'bash',
  '.sql': 'sql',
  '.swift': 'swift',
  '.toml': 'toml',
  '.ts': 'typescript',
  '.tsx': 'tsx',
  '.txt': 'text',
  '.vue': 'vue',
  '.xml': 'xml',
  '.yaml': 'yaml',
  '.yml': 'yaml',
  '.zsh': 'bash'
}

const LANGUAGE_BY_FILENAME: Record<string, string> = {
  '.env': 'dotenv',
  '.env.example': 'dotenv',
  '.gitignore': 'gitignore',
  Dockerfile: 'dockerfile',
  Makefile: 'makefile',
  README: 'markdown'
}

const MEDIA_TYPE_BY_EXTENSION: Record<string, string> = {
  '.css': 'text/css',
  '.csv': 'text/csv',
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.json': 'application/json',
  '.md': 'text/markdown',
  '.ts': 'text/typescript',
  '.tsx': 'text/tsx',
  '.txt': 'text/plain',
  '.vue': 'text/vue',
  '.xml': 'application/xml',
  '.yaml': 'application/yaml',
  '.yml': 'application/yaml'
}

type RuntimeConfig = {
  hermesAcpCwd?: string
}

type FilePreviewRequest = {
  path?: unknown
  workspace?: unknown
}

type ResolveFilePreviewPathsRequest = {
  paths?: unknown
  workspace?: unknown
}

export type AppFilePreviewReference = {
  path: string
  requestedPath: string
  relativePath?: string | null
  name: string
  mediaType: string
  size: number
  language?: string | null
  exists: boolean
}

export type AppFilePreview = AppFilePreviewReference & {
  content?: string | null
  truncated: boolean
  previewable: boolean
  reason?: string | null
}

export async function previewFile(config: RuntimeConfig, payload: FilePreviewRequest): Promise<AppFilePreview> {
  const requestedPath = cleanRequestedPath(payload.path)
  const workspaceRoot = await resolveWorkspaceRoot(config, payload.workspace)
  if (!workspaceRoot) throw httpError(400, 'Select a workspace before previewing relative files')

  const roots = await allowedRoots(workspaceRoot)
  const path = await resolvePreviewPath(requestedPath, workspaceRoot, roots)
  const info = await safeStat(path)
  if (!info?.isFile()) throw httpError(404, 'File not found')

  return await previewLocalFile(path, requestedPath, relativePreviewPath(path, roots))
}

export async function resolveFilePreviewPaths(config: RuntimeConfig, payload: ResolveFilePreviewPathsRequest) {
  const paths = Array.isArray(payload.paths) ? payload.paths.filter((path): path is string => typeof path === 'string') : []
  const workspaceRoot = await resolveWorkspaceRoot(config, payload.workspace)
  if (!workspaceRoot) return { files: [] as AppFilePreviewReference[] }

  const roots = await allowedRoots(workspaceRoot)
  const files: AppFilePreviewReference[] = []
  const seen = new Set<string>()

  for (const requestedPath of paths) {
    const value = requestedPath.trim()
    if (!value || seen.has(value)) continue
    seen.add(value)

    try {
      const path = await resolvePreviewPath(value, workspaceRoot, roots)
      const info = await safeStat(path)
      if (!info?.isFile()) continue
      files.push(await previewReference(path, value, roots))
    } catch {
      continue
    }
  }

  return { files }
}

function cleanRequestedPath(value: unknown) {
  const path = typeof value === 'string' ? value.trim() : ''
  if (!path) throw httpError(422, 'Path is required')
  return path
}

async function resolveWorkspaceRoot(config: RuntimeConfig, workspace: unknown) {
  const requested = typeof workspace === 'string' ? absolutePath(workspace) : ''
  if (requested) {
    const workspaces = await listWorkspaces(config)
    const allowed = workspaces.workspaces.some(candidate => candidate.path === requested)
    if (!allowed) throw httpError(400, 'Workspace is not configured')
    return requested
  }

  return config.hermesAcpCwd ? absolutePath(config.hermesAcpCwd) : null
}

async function allowedRoots(workspaceRoot: string) {
  const gitRoot = await gitRootFor(workspaceRoot)
  return uniquePaths([workspaceRoot, gitRoot || workspaceRoot].map(path => resolve(path)))
}

async function gitRootFor(workspaceRoot: string) {
  try {
    const { stdout } = await execFileAsync('git', ['-C', workspaceRoot, 'rev-parse', '--show-toplevel'], { timeout: 3000 })
    return stdout.trim() || null
  } catch {
    return null
  }
}

async function resolvePreviewPath(value: string, workspaceRoot: string, roots: string[]) {
  const expanded = expandHome(value)
  const candidates = isAbsolute(expanded)
    ? [resolve(expanded)]
    : uniquePaths([resolve(workspaceRoot, expanded), ...roots.map(root => resolve(root, expanded))])

  let escapedCandidate: string | null = null
  for (const candidate of candidates) {
    if (!roots.some(root => isWithin(candidate, root))) {
      escapedCandidate = candidate
      continue
    }
    if (await safeStat(candidate)) return candidate
  }

  if (escapedCandidate) throw httpError(400, 'File is outside the selected workspace')
  const fallback = candidates[0]
  if (!fallback) throw httpError(404, 'File not found')
  return fallback
}

async function previewLocalFile(path: string, requestedPath: string, relativePath: string | null): Promise<AppFilePreview> {
  const info = await stat(path)
  const mediaType = mediaTypeFor(path)
  const language = languageFor(path)
  const base = {
    path,
    requestedPath,
    relativePath,
    name: basename(path),
    mediaType,
    size: info.size,
    language
  }

  if (!await isTextPreviewable(path, mediaType)) {
    return {
      ...base,
      content: null,
      truncated: false,
      previewable: false,
      reason: 'File type cannot be previewed as text',
      exists: true
    }
  }

  const raw = await readFilePreviewBytes(path)
  const truncated = raw.length > MAX_FILE_PREVIEW_BYTES
  const content = raw.subarray(0, MAX_FILE_PREVIEW_BYTES).toString('utf8')

  return {
    ...base,
    content,
    truncated,
    previewable: true,
    exists: true
  }
}

async function previewReference(path: string, requestedPath: string, roots: string[]): Promise<AppFilePreviewReference> {
  const info = await stat(path)
  return {
    path,
    requestedPath,
    relativePath: relativePreviewPath(path, roots),
    name: basename(path),
    mediaType: mediaTypeFor(path),
    size: info.size,
    language: languageFor(path),
    exists: true
  }
}

async function readFilePreviewBytes(path: string) {
  const file = await import('node:fs/promises').then(fs => fs.open(path, 'r'))
  try {
    const buffer = Buffer.alloc(MAX_FILE_PREVIEW_BYTES + 1)
    const { bytesRead } = await file.read(buffer, 0, buffer.length, 0)
    return buffer.subarray(0, bytesRead)
  } finally {
    await file.close()
  }
}

async function isTextPreviewable(path: string, mediaType: string) {
  return TEXT_EXTENSIONS.has(extname(path)) || mediaType.startsWith('text/') || await looksLikeUtf8Text(path)
}

async function looksLikeUtf8Text(path: string) {
  const file = await import('node:fs/promises').then(fs => fs.open(path, 'r'))
  try {
    const buffer = Buffer.alloc(4096)
    const { bytesRead } = await file.read(buffer, 0, buffer.length, 0)
    const sample = buffer.subarray(0, bytesRead)
    if (sample.includes(0)) return false
    return Buffer.from(sample.toString('utf8'), 'utf8').equals(sample)
  } catch {
    return false
  } finally {
    await file.close()
  }
}

async function safeStat(path: string) {
  try {
    return await stat(path)
  } catch {
    return null
  }
}

function mediaTypeFor(path: string) {
  return MEDIA_TYPE_BY_EXTENSION[extname(path)] || 'application/octet-stream'
}

function languageFor(path: string) {
  const name = basename(path)
  return LANGUAGE_BY_FILENAME[name] || LANGUAGE_BY_EXTENSION[extname(path)] || null
}

function relativePreviewPath(path: string, roots: string[]) {
  for (const root of roots) {
    const value = relative(root, path)
    if (value && !value.startsWith('..') && !isAbsolute(value)) return value.split('/').join('/')
  }
  return null
}

function absolutePath(path: string) {
  return resolve(expandHome(path.trim()))
}

function expandHome(path: string) {
  if (path === '~') return homedir()
  if (path.startsWith('~/')) return join(homedir(), path.slice(2))
  if (path.startsWith('file://')) return fileURLToPath(path)
  return path
}

function isWithin(path: string, root: string) {
  const value = relative(root, path)
  return value === '' || Boolean(value && !value.startsWith('..') && !isAbsolute(value))
}

function uniquePaths(paths: string[]) {
  return Array.from(new Set(paths))
}

function httpError(statusCode: number, statusMessage: string) {
  return createError({ statusCode, statusMessage, message: statusMessage, data: { detail: statusMessage } })
}
