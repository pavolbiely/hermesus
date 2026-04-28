import type { WebChatMessage, WebChatPart } from '~/types/web-chat'

export type MessagePartGroup =
  | { type: 'process'; parts: WebChatPart[] }
  | { type: 'part'; part: WebChatPart }

const PROCESS_PART_TYPES = new Set(['reasoning', 'tool', 'status'])

export function partText(part: WebChatPart) {
  return typeof part.text === 'string' ? part.text : ''
}

function isProcessPart(part: WebChatPart) {
  return PROCESS_PART_TYPES.has(part.type)
}

export function groupMessageParts(parts: WebChatPart[]): MessagePartGroup[] {
  const groups: MessagePartGroup[] = []

  for (const part of parts) {
    const previous = groups.at(-1)
    if (isProcessPart(part) && previous?.type === 'process') {
      previous.parts.push(part)
      continue
    }

    groups.push(isProcessPart(part) ? { type: 'process', parts: [part] } : { type: 'part', part })
  }

  return groups
}

export function messagePartKey(message: WebChatMessage, part: WebChatPart) {
  const partIndex = message.parts.indexOf(part)
  return partIndex >= 0 ? `${message.id}:${partIndex}` : null
}

export function latestChangePartKey(messages: WebChatMessage[]) {
  for (let messageIndex = messages.length - 1; messageIndex >= 0; messageIndex -= 1) {
    const message = messages[messageIndex]
    if (!message) continue
    for (let partIndex = message.parts.length - 1; partIndex >= 0; partIndex -= 1) {
      const part = message.parts[partIndex]
      if (part?.type === 'changes' && part.changes?.files?.length) return `${message.id}:${partIndex}`
    }
  }

  return null
}

function toolName(part: WebChatPart) {
  return String(part.name || '').toLowerCase()
}

function isFailedTool(part: WebChatPart) {
  const status = String(part.status || '').toLowerCase()
  if (status.includes('fail') || status.includes('error')) return true

  const output = part.output
  if (output && typeof output === 'object' && 'exit_code' in output) {
    return Number((output as { exit_code?: unknown }).exit_code) !== 0
  }

  return false
}

function classifyTool(part: WebChatPart) {
  const name = toolName(part)
  if (['read_file', 'search_files'].includes(name)) return 'read'
  if (['patch', 'write_file'].includes(name)) return 'edit'
  if (['terminal', 'process'].includes(name)) return 'command'
  if (name.startsWith('browser_')) return 'browser'
  if (name.startsWith('mcp_') || name.includes('supabase') || name.includes('redis')) return 'api'
  return 'other'
}

function plural(count: number, singular: string, pluralValue = `${singular}s`) {
  return `${count} ${count === 1 ? singular : pluralValue}`
}

export function processGroupSummary(parts: WebChatPart[]) {
  const tools = parts.filter(part => part.type === 'tool')
  const reasoningCount = parts.filter(part => part.type === 'reasoning').length
  const statusCount = parts.filter(part => part.type === 'status').length
  const warningCount = parts.filter(part => part.type === 'status' && part.status === 'warn').length
  const failedCount = tools.filter(isFailedTool).length

  const counts = tools.reduce<Record<string, number>>((acc, part) => {
    const kind = classifyTool(part)
    acc[kind] = (acc[kind] || 0) + 1
    return acc
  }, {})

  const labels: string[] = []
  if (reasoningCount) labels.push('Reasoned')
  if (warningCount) labels.push(plural(warningCount, 'warning'))
  else if (statusCount) labels.push(plural(statusCount, 'status', 'statuses'))
  if (counts.read) labels.push(`read ${plural(counts.read, 'file')}`)
  if (counts.edit) labels.push(`edited ${plural(counts.edit, 'file')}`)
  if (counts.command) labels.push(`ran ${plural(counts.command, 'command')}`)
  if (counts.browser) labels.push(plural(counts.browser, 'browser action'))
  if (counts.api) labels.push(plural(counts.api, 'API call'))

  const knownCount = ['read', 'edit', 'command', 'browser', 'api'].reduce((sum, key) => sum + (counts[key] || 0), 0)
  const otherCount = tools.length - knownCount
  if (!labels.length && tools.length) labels.push(plural(tools.length, 'action'))
  else if (otherCount > 0) labels.push(plural(otherCount, 'other action'))

  if (failedCount) labels.push(`${failedCount} failed`)
  else if (tools.length) labels.push('completed')

  return labels.join(' · ')
}

export function messageText(message: WebChatMessage) {
  return message.parts.map(partText).filter(Boolean).join('\n\n')
}

function finitePositive(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null
}

function formatNumber(value: number) {
  return new Intl.NumberFormat(undefined, {
    notation: value >= 1000 ? 'compact' : 'standard',
    maximumFractionDigits: 1
  }).format(value)
}

function formatTokens(value: number) {
  return `${formatNumber(value)} ${value === 1 ? 'token' : 'tokens'}`
}

export function formatMessageTokenCount(message: WebChatMessage) {
  const count = finitePositive(message.tokenCount)
  return count ? formatTokens(count) : ''
}

export function messageTokenDetails(message: WebChatMessage) {
  const rows: { label: string, value: string }[] = []
  const input = finitePositive(message.inputTokens)
  const cacheRead = finitePositive(message.cacheReadTokens)
  const cacheWrite = finitePositive(message.cacheWriteTokens)
  const output = finitePositive(message.outputTokens)
  const reasoning = finitePositive(message.reasoningTokens)
  const apiCalls = finitePositive(message.apiCalls)

  if (input) rows.push({ label: 'Input', value: formatTokens(input) })
  if (cacheRead) rows.push({ label: 'Cache read', value: formatTokens(cacheRead) })
  if (cacheWrite) rows.push({ label: 'Cache write', value: formatTokens(cacheWrite) })
  if (output) rows.push({ label: 'Output', value: formatTokens(output) })
  if (reasoning) rows.push({ label: 'Reasoning', value: formatTokens(reasoning) })
  if (apiCalls) rows.push({ label: 'API calls', value: formatNumber(apiCalls) })

  if (!rows.length && finitePositive(message.tokenCount)) {
    rows.push({ label: message.role === 'user' ? 'Input' : 'Total', value: formatTokens(message.tokenCount as number) })
  }

  return rows
}

export function messageTokenTooltipNote(message: WebChatMessage) {
  if (message.role === 'user') {
    return 'Input usage for this turn, including sent context when reported by the provider.'
  }

  return 'Provider-reported usage for this agent turn. Exact scope depends on provider reporting.'
}

function formatDuration(milliseconds: number) {
  const seconds = milliseconds / 1000
  if (seconds < 60) return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: seconds < 10 ? 1 : 0 }).format(seconds)}s`

  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = Math.round(seconds % 60)
  return remainingSeconds ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`
}

export function formatMessageGenerationDuration(message: WebChatMessage) {
  const milliseconds = finitePositive(message.generationDurationMs)
  return milliseconds && milliseconds >= 1000 ? formatDuration(milliseconds) : ''
}

export function messageDurationDetails(message: WebChatMessage) {
  const rows: { label: string, value: string }[] = []
  const total = finitePositive(message.generationDurationMs)
  const model = finitePositive(message.modelDurationMs)
  const tools = finitePositive(message.toolDurationMs)
  const prompts = finitePositive(message.promptWaitDurationMs)

  if (total) rows.push({ label: 'Total', value: formatDuration(total) })
  if (model) rows.push({ label: 'Model / orchestration', value: formatDuration(model) })
  if (tools) rows.push({ label: 'Tools', value: formatDuration(tools) })
  if (prompts) rows.push({ label: 'Waiting for input', value: formatDuration(prompts) })

  return rows
}

export function messageDate(createdAt: string) {
  const date = new Date(createdAt)
  return Number.isFinite(date.getTime()) ? date : null
}

function isSameLocalDay(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate()
}

export function formatMessageTimestamp(createdAt: string, now = new Date()) {
  const date = messageDate(createdAt)
  if (!date) return ''

  const time = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(date)
  if (isSameLocalDay(date, now)) return time

  const dateFormatter = new Intl.DateTimeFormat(undefined, {
    day: 'numeric',
    month: 'short',
    year: date.getFullYear() === now.getFullYear() ? undefined : 'numeric'
  })

  return `${dateFormatter.format(date)}, ${time}`
}

export function messageTimestampTitle(createdAt: string) {
  return messageDate(createdAt)?.toLocaleString()
}
