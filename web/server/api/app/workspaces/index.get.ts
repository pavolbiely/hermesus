import { defineEventHandler } from 'h3'
import { useRuntimeConfig } from '#imports'
import { listWorkspaces } from '../../../app/workspaces'

export default defineEventHandler(async () => {
  return await listWorkspaces(useRuntimeConfig())
})
