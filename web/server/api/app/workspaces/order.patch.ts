import { defineEventHandler, readBody } from 'h3'
import { useRuntimeConfig } from '#imports'
import { reorderWorkspaces } from '../../../app/workspaces'

export default defineEventHandler(async (event) => {
  const body = await readBody<{ workspaceIds?: unknown }>(event)
  return await reorderWorkspaces(
    useRuntimeConfig(),
    Array.isArray(body.workspaceIds) ? body.workspaceIds.filter((id): id is string => typeof id === 'string') : []
  )
})
