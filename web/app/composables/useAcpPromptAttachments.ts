import type { ContentBlock } from '~/types/acp-api'
import type { ChatPromptAttachment } from '~/types/chat'

export type PendingAcpPrompt = {
  message: string
  attachments: ChatPromptAttachment[]
}

export function usePendingAcpPrompt() {
  return useState<Record<string, PendingAcpPrompt>>('pending-acp-prompts', () => ({}))
}

export function fileToPromptAttachment(file: File): Promise<ChatPromptAttachment> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error(`Could not read ${file.name}`))
    reader.onload = () => {
      const result = typeof reader.result === 'string' ? reader.result : ''
      const comma = result.indexOf(',')
      const data = comma >= 0 ? result.slice(comma + 1) : result
      resolve({
        id: crypto.randomUUID(),
        name: file.name,
        type: file.type || 'application/octet-stream',
        size: file.size,
        data
      })
    }
    reader.readAsDataURL(file)
  })
}

export async function filesToPromptAttachments(files: File[]) {
  return await Promise.all(files.map(fileToPromptAttachment))
}

export function attachmentsToPromptBlocks(message: string, attachments: ChatPromptAttachment[]): ContentBlock[] {
  const blocks: ContentBlock[] = [{ type: 'text', text: message }]

  attachments.forEach((attachment) => {
    if (attachment.type.startsWith('image/')) {
      blocks.push({
        type: 'image',
        data: attachment.data,
        mimeType: attachment.type,
        uri: `file://${attachment.name}`
      })
      return
    }

    blocks.push({
      type: 'resource',
      resource: {
        uri: `file://${attachment.name}`,
        mimeType: attachment.type,
        blob: attachment.data
      }
    })
  })

  return blocks
}
