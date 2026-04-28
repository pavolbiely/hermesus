export type ToolDetailSection = {
  label: string
  value: unknown
  text: string
  type: string
}

export type ToolDetailField = {
  label: string
  value: string
  code?: boolean
}

export type ToolDetailBlock = {
  label: string
  value: string
  kind?: 'text' | 'code'
}

export type ToolDetailOverview = {
  fields: ToolDetailField[]
  inputFields: ToolDetailField[]
  resultFields: ToolDetailField[]
  blocks: ToolDetailBlock[]
}

type ToolDetailPart = {
  name?: string | null
  status?: string | null
  input?: unknown
  output?: unknown
}

type RecordValue = Record<string, unknown>

const SENSITIVE_KEY_RE = /(token|password|passwd|secret|apikey|api_key|authorization|cookie|session.?token|bearer|jwt)/i
const FILE_PATH_RE = /^(path|file_path|workdir|cwd|url)$/i
const IMPORTANT_INPUT_KEYS = [
  'command',
  'workdir',
  'path',
  'file_path',
  'url',
  'query',
  'pattern',
  'ref',
  'key',
  'action',
  'session_id',
  'job_id',
  'timeout',
  'background',
  'text',
  'prompt'
]
const IMPORTANT_OUTPUT_KEYS = [
  'exit_code',
  'success',
  'error',
  'message',
  'total_count',
  'session_id',
  'job_id',
  'url',
  'path'
]

export function normalizeDetailValue(value: unknown) {
  if (typeof value !== 'string') return value

  const trimmed = value.trim()
  if (!trimmed || !['{', '['].includes(trimmed[0] || '')) return value

  try {
    return JSON.parse(trimmed)
  } catch {
    return value
  }
}

export function formatDetailValue(value: unknown) {
  const normalized = normalizeDetailValue(value)

  if (typeof normalized === 'string') return normalized
  if (normalized === undefined) return ''

  return JSON.stringify(normalized, null, 2)
}

export function detailValueType(value: unknown) {
  const normalized = normalizeDetailValue(value)
  if (Array.isArray(normalized)) return 'array'
  if (normalized === null) return 'null'
  return typeof normalized
}

export function hasDetailValue(value: unknown) {
  return value !== undefined && value !== null && value !== ''
}

export function toolDetailSections(part: { input?: unknown, output?: unknown }): ToolDetailSection[] {
  return [
    ['Input', part.input],
    ['Output', part.output]
  ]
    .filter(([, value]) => hasDetailValue(value))
    .map(([label, value]) => ({
      label: String(label),
      value,
      text: formatDetailValue(value),
      type: detailValueType(value)
    }))
}

export function valueSummary(value: unknown) {
  const normalized = normalizeDetailValue(value)

  if (Array.isArray(normalized)) return `${normalized.length} items`
  if (normalized && typeof normalized === 'object') {
    const record = normalized as RecordValue
    const parts: string[] = []

    if (typeof record.total_count === 'number') parts.push(`${record.total_count} total`)
    if (Array.isArray(record.files)) parts.push(`${record.files.length} files`)
    if (Array.isArray(record.items)) parts.push(`${record.items.length} items`)
    if (Array.isArray(record.results)) parts.push(`${record.results.length} results`)

    return parts.length ? parts.join(' · ') : `${Object.keys(record).length} keys`
  }

  const text = String(normalized ?? '').replace(/\s+/g, ' ').trim()
  return text.length > 56 ? `${text.slice(0, 56)}...` : text
}

export function toolDetailOverview(part: ToolDetailPart): ToolDetailOverview {
  const input = unwrapToolArguments(part.input)
  const output = normalizeDetailValue(part.output)
  const fields: ToolDetailField[] = []

  if (part.status) fields.push({ label: 'Status', value: humanizeStatus(part.status) })
  if (part.name) fields.push({ label: 'Tool', value: part.name })

  return {
    fields,
    inputFields: collectFields(input, IMPORTANT_INPUT_KEYS, 4),
    resultFields: collectOutputFields(output),
    blocks: collectOutputBlocks(output)
  }
}

function unwrapToolArguments(value: unknown) {
  const normalized = normalizeDetailValue(value)
  if (!isRecord(normalized)) return normalized

  if ('arguments' in normalized) return normalizeDetailValue(normalized.arguments)

  const fn = normalized.function
  if (isRecord(fn) && 'arguments' in fn) return normalizeDetailValue(fn.arguments)

  return normalized
}

function collectOutputFields(value: unknown) {
  const normalized = normalizeDetailValue(value)
  if (!isRecord(normalized)) return primitiveField('Result', normalized)

  const fields = collectFields(normalized, IMPORTANT_OUTPUT_KEYS, 4)

  for (const [key, label] of [
    ['files', 'Files'],
    ['matches', 'Matches'],
    ['items', 'Items'],
    ['results', 'Results']
  ] as const) {
    if (Array.isArray(normalized[key]) && !fields.some(field => field.label === label)) {
      fields.push({ label, value: String(normalized[key].length) })
    }
  }

  return fields
}

function collectOutputBlocks(value: unknown) {
  const normalized = normalizeDetailValue(value)
  if (typeof normalized === 'string') return [{ label: 'Output', value: normalized, kind: 'text' as const }]
  if (!isRecord(normalized)) return []

  const blocks: ToolDetailBlock[] = []
  for (const [key, label] of [
    ['command', 'Command'],
    ['output', 'Output'],
    ['stdout', 'Stdout'],
    ['stderr', 'Stderr'],
    ['error', 'Error'],
    ['diff', 'Diff'],
    ['content', 'Content']
  ] as const) {
    const value = normalized[key]
    if (typeof value === 'string' && value.trim()) {
      blocks.push({ label, value, kind: key === 'command' ? 'code' : 'text' })
    }
  }

  return blocks
}

function collectFields(value: unknown, preferredKeys: string[], maxFields: number) {
  const normalized = normalizeDetailValue(value)
  if (!isRecord(normalized)) return primitiveField('Value', normalized)

  return Object.entries(normalized)
    .filter(([key, entryValue]) => !SENSITIVE_KEY_RE.test(key) && isReadableFieldValue(entryValue))
    .sort(([a], [b]) => keyRank(a, preferredKeys) - keyRank(b, preferredKeys))
    .slice(0, maxFields)
    .map(([key, entryValue]) => ({
      label: humanizeKey(key),
      value: formatFieldValue(entryValue),
      code: FILE_PATH_RE.test(key) || key === 'command'
    }))
}

function primitiveField(label: string, value: unknown): ToolDetailField[] {
  if (!isReadableFieldValue(value)) return []
  return [{ label, value: formatFieldValue(value) }]
}

function isReadableFieldValue(value: unknown) {
  const normalized = normalizeDetailValue(value)
  if (normalized === undefined || normalized === null || normalized === '') return false
  if (typeof normalized === 'string') return normalized.trim().length > 0 && normalized.length <= 240
  if (typeof normalized === 'number' || typeof normalized === 'boolean') return true
  if (Array.isArray(normalized)) return true
  return isRecord(normalized) && Object.keys(normalized).length <= 3
}

function formatFieldValue(value: unknown) {
  const normalized = normalizeDetailValue(value)
  if (Array.isArray(normalized)) return `${normalized.length} ${normalized.length === 1 ? 'item' : 'items'}`
  if (isRecord(normalized)) return valueSummary(normalized)
  if (typeof normalized === 'boolean') return normalized ? 'Yes' : 'No'
  return String(normalized)
}

function keyRank(key: string, preferredKeys: string[]) {
  const preferredIndex = preferredKeys.indexOf(key)
  return preferredIndex === -1 ? preferredKeys.length + 1 : preferredIndex
}

function humanizeKey(key: string) {
  return key
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/^./, char => char.toUpperCase())
}

function humanizeStatus(status: string) {
  return status.replace(/_/g, ' ').replace(/^./, char => char.toUpperCase())
}

function isRecord(value: unknown): value is RecordValue {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
