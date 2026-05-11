import type { AcpChatMessage, AcpUsage } from '~/types/acp-chat'

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

function messageDate(createdAt: string) {
  const date = new Date(createdAt)
  return Number.isFinite(date.getTime()) ? date : null
}

function isSameLocalDay(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate()
}

function dateMs(value?: string | null) {
  if (!value) return null
  const time = new Date(value).getTime()
  return Number.isFinite(time) ? time : null
}

function formatDuration(milliseconds: number) {
  const seconds = milliseconds / 1000
  if (seconds < 60) return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: seconds < 10 ? 1 : 0 }).format(seconds)}s`

  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = Math.round(seconds % 60)
  return remainingSeconds ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`
}

export function acpMessageText(message: AcpChatMessage) {
  return message.parts
    .filter(part => part.type === 'text')
    .map(part => part.text)
    .filter(Boolean)
    .join('\n\n')
}

export function acpMessageSpeechText(message: AcpChatMessage) {
  return acpMessageText(message)
    .replace(/```[\s\S]*?```/g, ' code block ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/^\s{0,3}>\s?/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/[*_~#]/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export function formatAcpMessageTimestamp(createdAt: string, now = new Date()) {
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

export function acpMessageTimestampDetails(createdAt: string) {
  return messageDate(createdAt)?.toLocaleString() || ''
}

function acpUsageTotal(usage?: AcpUsage | null) {
  const reportedTotal = finitePositive(usage?.totalTokens)
  if (reportedTotal) return reportedTotal

  const derivedTotal = [
    finitePositive(usage?.inputTokens),
    finitePositive(usage?.outputTokens),
    finitePositive(usage?.thoughtTokens),
    finitePositive(usage?.cachedReadTokens),
    finitePositive(usage?.cachedWriteTokens)
  ].reduce<number>((total, value) => total + (value ?? 0), 0)

  return derivedTotal || null
}

export function formatAcpTokenCount(message: AcpChatMessage) {
  const total = acpUsageTotal(message.usage)
  return total ? formatTokens(total) : ''
}

export function acpTokenDetails(usage?: AcpUsage | null) {
  const rows: { label: string, value: string }[] = []
  const input = finitePositive(usage?.inputTokens)
  const output = finitePositive(usage?.outputTokens)
  const thought = finitePositive(usage?.thoughtTokens)
  const cacheRead = finitePositive(usage?.cachedReadTokens)
  const cacheWrite = finitePositive(usage?.cachedWriteTokens)
  const total = acpUsageTotal(usage)

  if (input) rows.push({ label: 'Input', value: formatTokens(input) })
  if (cacheRead) rows.push({ label: 'Cache read', value: formatTokens(cacheRead) })
  if (cacheWrite) rows.push({ label: 'Cache write', value: formatTokens(cacheWrite) })
  if (output) rows.push({ label: 'Output', value: formatTokens(output) })
  if (thought) rows.push({ label: 'Reasoning', value: formatTokens(thought) })
  if (total) rows.push({ label: 'Total', value: formatTokens(total) })

  return rows
}

export function formatAcpMessageDuration(message: AcpChatMessage) {
  const startedAt = dateMs(message.createdAt)
  const completedAt = dateMs(message.completedAt)
  if (!startedAt || !completedAt) return ''
  const duration = completedAt - startedAt
  return duration >= 1000 ? formatDuration(duration) : ''
}

export function acpMessageDurationDetails(message: AcpChatMessage) {
  const startedAt = dateMs(message.createdAt)
  const completedAt = dateMs(message.completedAt)
  if (!startedAt || !completedAt) return []

  return [
    { label: 'Started', value: new Date(startedAt).toLocaleTimeString() },
    { label: 'Completed', value: new Date(completedAt).toLocaleTimeString() },
    { label: 'Total', value: formatDuration(Math.max(0, completedAt - startedAt)) }
  ]
}
