import type { ContentBlock, PromptRequest } from '@agentclientprotocol/sdk'
import { createError, defineEventHandler, getRouterParam, readBody } from 'h3'
import { useRuntimeConfig } from '#imports'
import { getAcpBridge } from '../../../../acp/bridge'

type PromptBody = {
  message?: string
  messageId?: string
  prompt?: ContentBlock[]
  turnId?: string
}

function toPromptBlocks(body: PromptBody): ContentBlock[] {
  if (Array.isArray(body.prompt) && body.prompt.length > 0) return body.prompt
  if (typeof body.message === 'string' && body.message.trim()) {
    return [{ type: 'text', text: body.message }]
  }
  throw createError({ statusCode: 400, statusMessage: 'Prompt message is required' })
}

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig()
  const sessionId = getRouterParam(event, 'sessionId')
  if (!sessionId) {
    throw createError({ statusCode: 400, statusMessage: 'Missing sessionId' })
  }

  const body = await readBody<PromptBody>(event).catch((): PromptBody => ({}))
  const turnId = body.turnId || crypto.randomUUID()
  const messageId = body.messageId || crypto.randomUUID()
  const params: PromptRequest = {
    sessionId,
    messageId,
    prompt: toPromptBlocks(body)
  }

  void getAcpBridge().prompt(config, params, turnId).catch(() => undefined)

  return { sessionId, turnId, messageId, status: 'started' }
})
