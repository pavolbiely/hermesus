export type ToolDetailSection = {
  label: string
  value: unknown
  text: string
  type: string
}

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
    const record = normalized as Record<string, unknown>
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
