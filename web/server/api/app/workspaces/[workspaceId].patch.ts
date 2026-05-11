import { defineEventHandler, getRouterParam, readBody } from 'h3'
import { useRuntimeConfig } from '#imports'
import { updateWorkspace } from '../../../app/workspaces'

export default defineEventHandler(async (event) => {
  return await updateWorkspace(
    useRuntimeConfig(),
    getRouterParam(event, 'workspaceId') || '',
    await readBody(event)
  )
})
