import type { WebChatPart } from '../types/web-chat'

type RecordValue = Record<string, unknown>

type ToolCategory = 'Browser' | 'Files' | 'Terminal' | 'Hermes' | 'Database' | 'Memory' | 'Media' | 'Tasks' | 'User input' | 'MCP' | 'Tool'

type ToolDisplayDefinition = {
  label: string
  category: ToolCategory
  icon: string
}

export type ToolDisplayInfo = ToolDisplayDefinition & {
  rawName: string
  summary?: string
  title: string
}

const TOOL_DISPLAY_NAMES: Record<string, ToolDisplayDefinition> = {
  browser_back: { label: 'Go back in browser', category: 'Browser', icon: 'i-lucide-arrow-left' },
  browser_click: { label: 'Click in browser', category: 'Browser', icon: 'i-lucide-mouse-pointer-click' },
  browser_console: { label: 'Inspect browser console', category: 'Browser', icon: 'i-lucide-terminal-square' },
  browser_get_images: { label: 'List page images', category: 'Browser', icon: 'i-lucide-images' },
  browser_navigate: { label: 'Open browser page', category: 'Browser', icon: 'i-lucide-globe' },
  browser_press: { label: 'Press browser key', category: 'Browser', icon: 'i-lucide-keyboard' },
  browser_scroll: { label: 'Scroll browser page', category: 'Browser', icon: 'i-lucide-move-vertical' },
  browser_snapshot: { label: 'Inspect browser page', category: 'Browser', icon: 'i-lucide-scan-text' },
  browser_type: { label: 'Type in browser', category: 'Browser', icon: 'i-lucide-keyboard' },
  browser_vision: { label: 'Analyze browser screenshot', category: 'Browser', icon: 'i-lucide-eye' },

  read_file: { label: 'Read file', category: 'Files', icon: 'i-lucide-file-text' },
  write_file: { label: 'Write file', category: 'Files', icon: 'i-lucide-file-plus' },
  search_files: { label: 'Search files', category: 'Files', icon: 'i-lucide-search' },
  patch: { label: 'Edit file', category: 'Files', icon: 'i-lucide-file-pen' },

  terminal: { label: 'Run terminal command', category: 'Terminal', icon: 'i-lucide-terminal' },
  process: { label: 'Manage process', category: 'Terminal', icon: 'i-lucide-activity' },
  execute_code: { label: 'Run Python script', category: 'Terminal', icon: 'i-lucide-file-code-2' },

  todo: { label: 'Update task list', category: 'Tasks', icon: 'i-lucide-list-checks' },
  delegate_task: { label: 'Delegate task', category: 'Tasks', icon: 'i-lucide-network' },
  cronjob: { label: 'Manage scheduled job', category: 'Tasks', icon: 'i-lucide-calendar-clock' },
  'multi_tool_use.parallel': { label: 'Run tools in parallel', category: 'Tasks', icon: 'i-lucide-git-branch-plus' },

  skills_list: { label: 'List skills', category: 'Hermes', icon: 'i-lucide-library' },
  skill_view: { label: 'Load skill', category: 'Hermes', icon: 'i-lucide-book-open' },
  skill_manage: { label: 'Manage skill', category: 'Hermes', icon: 'i-lucide-book-marked' },
  memory: { label: 'Update memory', category: 'Memory', icon: 'i-lucide-cpu' },
  session_search: { label: 'Search past sessions', category: 'Memory', icon: 'i-lucide-history' },

  clarify: { label: 'Ask user', category: 'User input', icon: 'i-lucide-circle-help' },

  vision_analyze: { label: 'Analyze image', category: 'Media', icon: 'i-lucide-eye' },
  image_generate: { label: 'Generate image', category: 'Media', icon: 'i-lucide-image-plus' },
  text_to_speech: { label: 'Create speech audio', category: 'Media', icon: 'i-lucide-volume-2' },

  mcp_supabase_apply_migration: { label: 'Supabase: Apply migration', category: 'Database', icon: 'i-lucide-database' },
  mcp_supabase_execute_sql: { label: 'Supabase: Run SQL', category: 'Database', icon: 'i-lucide-database' },
  mcp_supabase_generate_typescript_types: { label: 'Supabase: Generate TypeScript types', category: 'Database', icon: 'i-lucide-file-code-2' },
  mcp_supabase_get_advisors: { label: 'Supabase: Check advisors', category: 'Database', icon: 'i-lucide-shield-check' },
  mcp_supabase_get_logs: { label: 'Supabase: Get logs', category: 'Database', icon: 'i-lucide-scroll-text' },
  mcp_supabase_get_project_url: { label: 'Supabase: Get project URL', category: 'Database', icon: 'i-lucide-link' },
  mcp_supabase_get_publishable_keys: { label: 'Supabase: List publishable keys', category: 'Database', icon: 'i-lucide-key-round' },
  mcp_supabase_list_extensions: { label: 'Supabase: List extensions', category: 'Database', icon: 'i-lucide-plug' },
  mcp_supabase_list_migrations: { label: 'Supabase: List migrations', category: 'Database', icon: 'i-lucide-list' },
  mcp_supabase_list_tables: { label: 'Supabase: List tables', category: 'Database', icon: 'i-lucide-table-2' },
  mcp_supabase_search_docs: { label: 'Supabase: Search docs', category: 'Database', icon: 'i-lucide-book-open' },
  mcp_supabase_list_prompts: { label: 'Supabase: List prompts', category: 'Database', icon: 'i-lucide-list' },
  mcp_supabase_get_prompt: { label: 'Supabase: Get prompt', category: 'Database', icon: 'i-lucide-file-text' },
  mcp_supabase_list_resources: { label: 'Supabase: List resources', category: 'Database', icon: 'i-lucide-list-tree' },
  mcp_supabase_read_resource: { label: 'Supabase: Read resource', category: 'Database', icon: 'i-lucide-file-text' },

  mcp_redis_get: { label: 'Redis: Get value', category: 'MCP', icon: 'i-lucide-database' },
  mcp_redis_set: { label: 'Redis: Set value', category: 'MCP', icon: 'i-lucide-database' },
  mcp_redis_delete: { label: 'Redis: Delete value', category: 'MCP', icon: 'i-lucide-trash-2' },
  mcp_redis_list: { label: 'Redis: List keys', category: 'MCP', icon: 'i-lucide-list' },
  mcp_redis_list_prompts: { label: 'Redis: List prompts', category: 'MCP', icon: 'i-lucide-list' },
  mcp_redis_get_prompt: { label: 'Redis: Get prompt', category: 'MCP', icon: 'i-lucide-file-text' },
  mcp_redis_list_resources: { label: 'Redis: List resources', category: 'MCP', icon: 'i-lucide-list-tree' },
  mcp_redis_read_resource: { label: 'Redis: Read resource', category: 'MCP', icon: 'i-lucide-file-text' }
}


type Candidate = {
  key: string
  value: string
  score: number
}

const PREFERRED_KEYS = [
  'name',
  'path',
  'file_path',
  'command',
  'query',
  'pattern',
  'url',
  'ref',
  'key',
  'action',
  'job_id',
  'session_id',
  'prompt',
  'title',
  'text',
  'schedule'
]

const SENSITIVE_KEY_RE = /(token|password|passwd|secret|apikey|api_key|authorization|cookie|session.?token|bearer|jwt)/i
const PATH_KEY_RE = /(path|file|dir|workdir|cwd|url)$/i
const TEXT_KEY_RE = /(prompt|text|content|description|message|query|command|pattern)$/i
const MAX_SUMMARY_LENGTH = 84


function fallbackToolDefinition(rawName: string): ToolDisplayDefinition {
  const name = rawName.replace(/^functions\./, '')

  if (name.startsWith('mcp_supabase_')) {
    return { label: `Supabase: ${humanizeToolAction(name.slice('mcp_supabase_'.length))}`, category: 'Database', icon: 'i-lucide-database' }
  }

  if (name.startsWith('mcp_redis_')) {
    return { label: `Redis: ${humanizeToolAction(name.slice('mcp_redis_'.length))}`, category: 'MCP', icon: 'i-lucide-database' }
  }

  if (name.startsWith('mcp_')) {
    const [, server, ...actionParts] = name.split('_')
    const serverLabel = server ? titleCase(server) : 'MCP'
    return { label: `${serverLabel}: ${humanizeToolAction(actionParts.join('_') || name)}`, category: 'MCP', icon: 'i-lucide-plug' }
  }

  return { label: humanizeToolAction(name), category: 'Tool', icon: 'i-lucide-wrench' }
}

function humanizeToolAction(value: string) {
  return value
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .trim()
    .replace(/^./, char => char.toUpperCase())
}

function titleCase(value: string) {
  return value.replace(/^./, char => char.toUpperCase())
}

function normalizeSummaryValue(value: unknown) {
  if (typeof value !== 'string') return value

  const trimmed = value.trim()
  if (!trimmed || !['{', '['].includes(trimmed[0] || '')) return value

  try {
    return JSON.parse(trimmed)
  } catch {
    return value
  }
}

function parseJsonishString(value: unknown) {
  if (typeof value !== 'string') return value

  const trimmed = value.trim()
  if (!trimmed || !['{', '['].includes(trimmed[0] || '')) return value

  try {
    return JSON.parse(trimmed)
  } catch {
    return value
  }
}

function firstJsonKey(value: unknown) {
  const record = normalizeToolPayload(value)
  if (!record) return undefined
  return Object.keys(record).find(key => record[key] !== undefined && record[key] !== null && record[key] !== '')
}

function normalizeToolPayload(value: unknown): RecordValue | undefined {
  const normalized = normalizeSummaryValue(value)
  return normalized && typeof normalized === 'object' && !Array.isArray(normalized)
    ? normalized as RecordValue
    : undefined
}

function isSensitiveKey(key: string) {
  return SENSITIVE_KEY_RE.test(key)
}

function compactText(value: string, maxLength = MAX_SUMMARY_LENGTH) {
  const text = value.replace(/\s+/g, ' ').trim()
  if (text.length <= maxLength) return text
  return `${text.slice(0, maxLength - 1)}…`
}

function compactPath(value: string) {
  const text = compactText(value, 120)
  if (/^https?:\/\//i.test(text)) {
    try {
      const url = new URL(text)
      return compactText(`${url.hostname}${url.pathname === '/' ? '' : url.pathname}`)
    } catch {
      return text
    }
  }

  return text.replace(/^\/Users\/[^/]+\//, '~/')
}

function primitiveSummary(key: string, value: unknown) {
  if (isSensitiveKey(key)) return undefined
  if (typeof value === 'string') {
    const text = value.trim()
    if (!text) return undefined
    return PATH_KEY_RE.test(key) ? compactPath(text) : compactText(text)
  }
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return undefined
}

function keyScore(key: string, value: unknown, depth: number) {
  const lower = key.toLowerCase()
  const preferredIndex = PREFERRED_KEYS.indexOf(lower)
  let score = preferredIndex >= 0 ? 120 - preferredIndex : 20

  if (typeof value === 'string') {
    if (PATH_KEY_RE.test(key) || /^https?:\/\//i.test(value) || value.includes('/')) score += 18
    if (TEXT_KEY_RE.test(key)) score += 12
    if (value.length > 160) score -= 12
  }

  if (typeof value === 'number') score -= 10
  score -= depth * 8
  return score
}

function collectCandidates(value: unknown, toolName = '', depth = 0): Candidate[] {
  if (depth > 3) return []

  const normalized = normalizeSummaryValue(value)
  if (!normalized || typeof normalized !== 'object' || Array.isArray(normalized)) return []

  const candidates: Candidate[] = []
  for (const [key, child] of Object.entries(normalized as RecordValue)) {
    if (isSensitiveKey(key)) continue

    const childValue = key === 'arguments' ? parseJsonishString(child) : child
    const primitive = primitiveSummary(key, childValue)
    if (primitive && primitive.toLowerCase() !== toolName.toLowerCase()) {
      candidates.push({ key, value: primitive, score: keyScore(key, child, depth) })
      continue
    }

    if (childValue && typeof childValue === 'object' && !Array.isArray(childValue)) {
      candidates.push(...collectCandidates(childValue, toolName, depth + 1))
    }
  }

  return candidates
}

function argumentPayload(input: unknown) {
  const record = normalizeToolPayload(input)
  if (!record) return undefined

  if ('arguments' in record) return parseJsonishString(record.arguments)

  const fn = record.function
  if (fn && typeof fn === 'object' && !Array.isArray(fn) && 'arguments' in fn) {
    return parseJsonishString((fn as RecordValue).arguments)
  }

  return undefined
}

function candidateByKey(candidates: Candidate[], key: string) {
  return candidates.find(candidate => candidate.key.toLowerCase() === key)
}

function candidateSummary(candidates: Candidate[]) {
  const action = candidateByKey(candidates, 'action')
  const target = candidates.find(candidate => candidate !== action)
  if (action && target) return compactText(`${action.value} ${target.value}`)

  return candidates[0]?.value
}

function bestInputSummary(input: unknown, toolName = '') {
  const args = argumentPayload(input)
  if (args !== undefined) {
    const argCandidates = collectCandidates(args, toolName).sort((a, b) => b.score - a.score)
    const argSummary = candidateSummary(argCandidates)
    if (argSummary) return argSummary
  }

  const normalized = normalizeSummaryValue(input)

  if (typeof normalized === 'string') return compactText(normalized)
  if (Array.isArray(normalized)) return `${normalized.length} items`
  if (!normalized || typeof normalized !== 'object') return primitiveSummary('value', normalized)

  const candidates = collectCandidates(normalized, toolName).sort((a, b) => b.score - a.score)
  const summary = candidateSummary(candidates)
  if (summary) return summary

  return `${Object.keys(normalized as RecordValue).length} keys`
}

function outputStatusSummary(output: unknown) {
  const normalized = normalizeSummaryValue(output)

  if (normalized && typeof normalized === 'object' && !Array.isArray(normalized)) {
    const record = normalized as RecordValue
    const error = primitiveSummary('error', record.error) || primitiveSummary('message', record.message)
    if (record.success === false && error) return error
    if (typeof record.exit_code === 'number') return record.exit_code === 0 ? 'passed' : `failed (${record.exit_code})`
    if (Array.isArray(record.files_modified)) return `${record.files_modified.length} files changed`
    if (typeof record.total_count === 'number') return `${record.total_count} matches`
    if (Array.isArray(record.matches)) return `${record.matches.length} matches`
    if (Array.isArray(record.files)) return `${record.files.length} files`
    if (Array.isArray(record.items)) return `${record.items.length} items`
    if (Array.isArray(record.results)) return `${record.results.length} results`
    if (record.success === true) return 'done'
  }

  if (Array.isArray(normalized)) return `${normalized.length} items`
  if (typeof normalized === 'string') return compactText(normalized)
  return undefined
}

export function toolRawName(part: Pick<WebChatPart, 'name' | 'input'>) {
  const name = typeof part.name === 'string' ? part.name.trim() : ''
  if (name && name !== 'Tool call') return name

  const input = normalizeToolPayload(part.input)
  const functionName = input?.function && typeof input.function === 'object'
    ? (input.function as RecordValue).name
    : undefined
  if (typeof functionName === 'string' && functionName.trim()) return functionName.trim()

  return firstJsonKey(part.input) || 'Tool call'
}

export function toolDisplayInfo(part: Pick<WebChatPart, 'name' | 'input'>): ToolDisplayInfo {
  const rawName = toolRawName(part)
  const lookupName = rawName.replace(/^functions\./, '')
  const definition = TOOL_DISPLAY_NAMES[lookupName] || fallbackToolDefinition(rawName)
  const summary = toolInputSummary(part)

  return {
    ...definition,
    rawName,
    summary,
    title: summary ? `${definition.label}: ${summary}` : definition.label
  }
}

export function toolDisplayName(part: Pick<WebChatPart, 'name' | 'input'>) {
  return toolDisplayInfo(part).label
}

export function toolInputSummary(part: Pick<WebChatPart, 'name' | 'input'>) {
  return bestInputSummary(part.input, toolRawName(part))
}

export function toolOutputSummary(part: Pick<WebChatPart, 'output' | 'status'>) {
  return outputStatusSummary(part.output) || part.status || undefined
}

export function toolCallTitle(part: Pick<WebChatPart, 'name' | 'input'>) {
  return toolDisplayInfo(part).title
}
