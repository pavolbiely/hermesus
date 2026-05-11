import { defineEventHandler, readBody } from 'h3'
import { useRuntimeConfig } from '#imports'
import { previewFile } from '../../../app/filePreviews'

export default defineEventHandler(async (event) => {
  return await previewFile(useRuntimeConfig(), await readBody(event))
})
