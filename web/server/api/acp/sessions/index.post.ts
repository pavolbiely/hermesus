import type { NewSessionRequest } from '@agentclientprotocol/sdk'
import { defineEventHandler, readBody } from 'h3'
import { useRuntimeConfig } from '#imports'
import { getAcpBridge } from '../../../acp/bridge'

type NewSessionBody = Partial<NewSessionRequest>

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig()
  const body = await readBody<NewSessionBody>(event).catch((): NewSessionBody => ({}))

  const params: NewSessionRequest = {
    cwd: body.cwd || config.hermesAcpCwd,
    mcpServers: body.mcpServers || [],
    ...(body.additionalDirectories ? { additionalDirectories: body.additionalDirectories } : {})
  }

  return getAcpBridge().newSession(config, params)
})
