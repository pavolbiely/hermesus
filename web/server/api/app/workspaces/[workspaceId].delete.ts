import { defineEventHandler, getRouterParam } from 'h3'
import { useRuntimeConfig } from '#imports'
import { deleteWorkspace } from '../../../app/workspaces'

export default defineEventHandler(async (event) => {
  return await deleteWorkspace(useRuntimeConfig(), getRouterParam(event, 'workspaceId') || '')
})
