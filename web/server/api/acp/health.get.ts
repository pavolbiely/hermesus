import { defineEventHandler } from 'h3'
import { useRuntimeConfig } from '#imports'
import { getAcpBridge } from '../../acp/bridge'

export default defineEventHandler(() => {
  return getAcpBridge().health(useRuntimeConfig())
})
