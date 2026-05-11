import { defineEventHandler, getQuery } from 'h3'
import { suggestWorkspaceDirectories } from '../../../app/workspaces'

export default defineEventHandler(async (event) => {
  const prefix = getQuery(event).prefix
  return await suggestWorkspaceDirectories(typeof prefix === 'string' ? prefix : '')
})
