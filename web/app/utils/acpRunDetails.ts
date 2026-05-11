import type { AcpChatMessage, AcpChatPart } from '../types/acp-chat'

export type AcpToolPart = Extract<AcpChatPart, { type: 'tool' }>

export type AcpRunDetailGroup = {
  id: string
  thoughtText: string
  thoughtDetail: string
  tools: AcpToolPart[]
}

export function reasoningText(message: AcpChatMessage) {
  return message.parts.filter(part => part.type === 'reasoning').map(part => part.text).join('')
}

export function hasThoughtActivity(message: AcpChatMessage) {
  return Boolean(reasoningText(message).trim() || thoughtTokenCount(message))
}

export function thoughtTokenCount(message: AcpChatMessage) {
  return message.usage?.thoughtTokens && message.usage.thoughtTokens > 0 ? message.usage.thoughtTokens : 0
}

export function thoughtDetail(message: AcpChatMessage) {
  const tokens = thoughtTokenCount(message)
  if (!tokens) return ''
  return `${tokens.toLocaleString()} thought token${tokens === 1 ? '' : 's'} were used for this turn. Hermes ACP did not expose the raw thought text for this model response.`
}

export function toolParts(message: AcpChatMessage): AcpToolPart[] {
  return message.parts.filter((part): part is AcpToolPart => part.type === 'tool')
}

export function runDetailGroups(message: AcpChatMessage): AcpRunDetailGroup[] {
  const groups: AcpRunDetailGroup[] = []
  let current: AcpRunDetailGroup | null = null

  const startGroup = (index: number, thoughtText = '') => {
    current = {
      id: `${message.id}-run-group-${index}`,
      thoughtText,
      thoughtDetail: '',
      tools: []
    }
    groups.push(current)
    return current
  }

  message.parts.forEach((part, index) => {
    if (part.type === 'reasoning') {
      if (!part.text.trim()) return

      if (current?.thoughtText && current.tools.length === 0) {
        current.thoughtText += part.text
        return
      }

      startGroup(index, part.text)
      return
    }

    if (part.type === 'tool') {
      const group = current ?? startGroup(index)
      group.tools.push(part)
    }
  })

  const fallbackDetail = thoughtDetail(message)
  if (fallbackDetail && !groups.some(group => group.thoughtText.trim() || group.thoughtDetail.trim())) {
    const group = groups[0] ?? startGroup(0)
    group.thoughtDetail = fallbackDetail
  }

  return groups
}
