import { defineEventHandler, readBody } from 'h3'
import { useRuntimeConfig } from '#imports'
import { resolveFilePreviewPaths } from '../../../app/filePreviews'

export default defineEventHandler(async (event) => {
  return await resolveFilePreviewPaths(useRuntimeConfig(), await readBody(event))
})
