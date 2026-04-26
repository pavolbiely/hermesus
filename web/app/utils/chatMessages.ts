import type { WebChatMessage, WebChatPart } from '~/types/web-chat'

export type MessagePartGroup =
  | { type: 'tools', parts: WebChatPart[] }
  | { type: 'part', part: WebChatPart }

export function partText(part: WebChatPart) {
  return typeof part.text === 'string' ? part.text : ''
}

export function groupMessageParts(parts: WebChatPart[]): MessagePartGroup[] {
  const groups: MessagePartGroup[] = []

  for (const part of parts) {
    const previous = groups.at(-1)
    if (part.type === 'tool' && previous?.type === 'tools') {
      previous.parts.push(part)
      continue
    }

    groups.push(part.type === 'tool' ? { type: 'tools', parts: [part] } : { type: 'part', part })
  }

  return groups
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
