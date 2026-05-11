import type { AcpChatMessage } from '../types/acp-chat'
import { hasThoughtActivity } from './acpRunDetails'

type AttachmentPart = Extract<AcpChatMessage['parts'][number], { type: 'attachment' }>

export type AcpChatFilePart = {
  type: 'file'
  id?: string
  filename: string
  mediaType: string
  size?: number
  url: string
}

export type AcpChatDisplayMessage = Omit<AcpChatMessage, 'parts'> & {
  parts: (Exclude<AcpChatMessage['parts'][number], AttachmentPart> | AcpChatFilePart)[]
}

export function partText(message: AcpChatMessage) {
  return message.parts.filter(part => part.type === 'text').map(part => part.text).join('')
}

export function systemEventTitle(message: AcpChatMessage) {
  const eventPart = message.parts.find(part => part.type === 'event')
  return eventPart?.type === 'event' ? eventPart.title : 'System event'
}

export function systemEventSeverity(message: AcpChatMessage) {
  const eventPart = message.parts.find(part => part.type === 'event')
  return eventPart?.type === 'event' ? eventPart.severity || 'info' : 'info'
}

export function groupProcessMessages(source: AcpChatMessage[]): AcpChatMessage[] {
  const grouped: AcpChatMessage[] = []

  for (const message of source) {
    const clone = cloneChatMessage(message)
    const previous = grouped[grouped.length - 1]
    if (previous && shouldMergeAssistantProcessMessage(previous, clone)) {
      previous.parts.push(...clone.parts)
      previous.id = `${previous.id}:${clone.id}`
      continue
    }
    grouped.push(clone)
  }

  return grouped
}

export function shouldMergeAssistantProcessMessage(previous: AcpChatMessage, next: AcpChatMessage) {
  if (previous.role !== 'assistant' || next.role !== 'assistant') return false
  if (hasTextParts(previous) || hasTextParts(next)) return false
  return hasProcessParts(previous) && hasProcessParts(next)
}

export function cloneChatMessage(message: AcpChatMessage): AcpChatMessage {
  return {
    ...message,
    parts: message.parts.map(part => ({ ...part }))
  }
}

export function attachmentsAsFileParts<T extends AcpChatMessage>(message: T): Omit<T, 'parts'> & AcpChatDisplayMessage {
  return {
    ...message,
    parts: message.parts.map((part) => {
      if (part.type !== 'attachment') return { ...part }
      return attachmentAsFilePart(part)
    })
  }
}

function attachmentAsFilePart(attachment: AttachmentPart): AcpChatFilePart {
  return {
    type: 'file',
    id: attachment.id,
    filename: attachment.name,
    mediaType: attachment.mediaType,
    size: attachment.size,
    url: attachment.data ? `data:${attachment.mediaType};base64,${attachment.data}` : ''
  }
}

export function hasTextParts(message: AcpChatMessage) {
  return message.parts.some(part => part.type === 'text' && part.text.trim())
}

export function hasProcessParts(message: AcpChatMessage) {
  return message.parts.some(part => part.type === 'tool' || part.type === 'reasoning' || part.type === 'event') || hasThoughtActivity(message)
}
