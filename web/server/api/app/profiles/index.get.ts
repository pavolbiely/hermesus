import { defineEventHandler } from 'h3'
import { listProfiles } from '../../../app/profiles'

export default defineEventHandler(async () => {
  return await listProfiles()
})
