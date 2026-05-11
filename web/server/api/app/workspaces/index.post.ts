import { defineEventHandler, readBody, setResponseStatus } from 'h3'
import { useRuntimeConfig } from '#imports'
import { createWorkspace } from '../../../app/workspaces'

export default defineEventHandler(async (event) => {
  const result = await createWorkspace(useRuntimeConfig(), await readBody(event))
  setResponseStatus(event, 201)
  return result
})
