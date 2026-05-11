import type { NewSessionRequest } from '@agentclientprotocol/sdk'
import { defineEventHandler, readBody } from 'h3'
import { useRuntimeConfig } from '#imports'
import { getAcpBridge } from '../../../acp/bridge'
import { patchAcpSessionMetadata } from '../../../app/acpSessionMetadata'

type NewSessionBody = Partial<NewSessionRequest>

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig()
  const body = await readBody<NewSessionBody>(event).catch((): NewSessionBody => ({}))
  const hasWorkspace = Object.prototype.hasOwnProperty.call(body, 'cwd')
  const workspace = typeof body.cwd === 'string' && body.cwd.trim() ? body.cwd.trim() : null

  const params: NewSessionRequest = {
    cwd: workspace || config.hermesAcpCwd,
    mcpServers: body.mcpServers || [],
    ...(body.additionalDirectories ? { additionalDirectories: body.additionalDirectories } : {})
  }

  const response = await getAcpBridge().newSession(config, params)
  if (hasWorkspace) await patchAcpSessionMetadata(config, response.sessionId, { workspace })
  return response
})
