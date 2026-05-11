import { defineEventHandler } from 'h3'
import { useRuntimeConfig } from '#imports'
import { getAcpBridge } from '../../acp/bridge'

export default defineEventHandler(async () => {
  const config = useRuntimeConfig()
  const initialize = await getAcpBridge().initialize(config)
  return {
    initialize,
    health: getAcpBridge().health(config)
  }
})
