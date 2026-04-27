import type { WebChatMessage, WebChatPart } from '~/types/web-chat'

export type MessagePartGroup =
  | { type: 'process'; parts: WebChatPart[] }
  | { type: 'part'; part: WebChatPart }

const PROCESS_PART_TYPES = new Set(['reasoning', 'tool'])

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
  const failedCount = tools.filter(isFailedTool).length

  const counts = tools.reduce<Record<string, number>>((acc, part) => {
    const kind = classifyTool(part)
    acc[kind] = (acc[kind] || 0) + 1
    return acc
  }, {})

  const labels: string[] = []
  if (reasoningCount) labels.push('Reasoned')
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
