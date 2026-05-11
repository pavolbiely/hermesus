import type { AcpChatMessage } from '../types/acp-chat'
import { hasThoughtActivity, reasoningText, toolParts, type AcpToolPart } from './acpRunDetails'
import { toolActivityTitle } from './toolCalls'
import { hasTextParts, partText } from './acpChatMessageDisplay'

export function runDetailSummary(message: AcpChatMessage) {
  const tools = toolParts(message)
  const failed = tools.filter(part => part.error || part.status === 'failed').length
  const running = runningToolParts(message).length
  const counts = tools.reduce<Record<string, number>>((acc, part) => {
    const kind = classifyToolPart(part)
    acc[kind] = (acc[kind] || 0) + 1
    return acc
  }, {})
  const labels: string[] = []

  if (hasThoughtActivity(message)) labels.push('Reasoned')
  if (counts.read) labels.push(`read ${plural(counts.read, 'file')}`)
  if (counts.edit) labels.push(`edited ${plural(counts.edit, 'file')}`)
  if (counts.command) labels.push(`ran ${plural(counts.command, 'command')}`)
  if (counts.browser) labels.push(plural(counts.browser, 'browser action'))
  if (counts.api) labels.push(plural(counts.api, 'API call'))

  const known = ['read', 'edit', 'command', 'browser', 'api'].reduce((sum, key) => sum + (counts[key] || 0), 0)
  const other = tools.length - known
  if (!labels.length && tools.length) labels.push(plural(tools.length, 'action'))
  else if (other > 0) labels.push(plural(other, 'other action'))

  if (failed) labels.push(`${failed} failed`)
  else if (running) labels.push(`${running} running`)
  else if (tools.length) labels.push('completed')

  return labels.join(' · ')
}

export function classifyToolPart(part: AcpToolPart) {
  const value = `${part.name || ''} ${part.kind || ''}`.toLowerCase()
  if (value.includes('read') || value.includes('search')) return 'read'
  if (value.includes('patch') || value.includes('write') || value.includes('edit')) return 'edit'
  if (value.includes('terminal') || value.includes('process') || value.includes('command')) return 'command'
  if (value.includes('browser')) return 'browser'
  if (value.includes('mcp') || value.includes('api') || value.includes('supabase') || value.includes('redis')) return 'api'
  return 'other'
}

export function plural(count: number, singular: string, pluralValue = `${singular}s`) {
  return `${count} ${count === 1 ? singular : pluralValue}`
}

export function runningToolParts(message: AcpChatMessage) {
  return toolParts(message).filter(part => part.state !== 'completed' && !part.error)
}

export function runActivityLabel(message: AcpChatMessage, activeTurnId: string | null) {
  const runningTool = runningToolParts(message)[0]
  if (runningTool) return `Running ${toolActivityTitle(runningTool)}`
  if (message.turnId && message.turnId === activeTurnId && reasoningText(message).trim()) return 'Thinking'
  if (message.role === 'assistant' && hasTextParts(message)) return 'Responding…'
  return ''
}

export function hasRunDetails(message: AcpChatMessage) {
  return toolParts(message).length > 0 || hasThoughtActivity(message)
}

export function shouldRenderRunDetailsBeforeMessage(message: AcpChatMessage, activeTurnId: string | null) {
  return Boolean(activeTurnId && message.turnId === activeTurnId && hasRunDetails(message))
}

export function runDetailsSpacingClass(message: AcpChatMessage, position: 'before' | 'after', hasFooter = false) {
  if (position === 'before') return partText(message) ? 'mb-4' : 'mb-2'
  return hasFooter || partText(message) ? 'mt-4' : 'mt-2'
}
