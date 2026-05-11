import { execFile } from 'node:child_process'
import { promisify } from 'node:util'

const execFileAsync = promisify(execFile)

type HermesProfile = {
  id: string
  label: string
  active: boolean
}

type HermesProfilesResponse = {
  profiles: HermesProfile[]
  activeProfile: string | null
}

export async function listProfiles(): Promise<HermesProfilesResponse> {
  const { stdout } = await execFileAsync('hermes', ['profile', 'list'], { timeout: 10_000 })
  return parseProfileList(stdout)
}

export function parseProfileList(output: string): HermesProfilesResponse {
  const profiles = new Map<string, HermesProfile>()
  let activeProfile: string | null = null

  for (const line of output.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('Profile') || trimmed.startsWith('─')) continue

    const active = trimmed.startsWith('◆')
    const normalized = active ? trimmed.slice(1).trimStart() : trimmed
    const [id] = normalized.split(/\s{2,}/)
    if (!id || id === 'Profile') continue

    const profile = profiles.get(id) || { id, label: id, active: false }
    if (active) {
      profile.active = true
      activeProfile = id
    }
    profiles.set(id, profile)
  }

  if (!activeProfile && profiles.has('default')) {
    activeProfile = 'default'
    const defaultProfile = profiles.get('default')
    if (defaultProfile) defaultProfile.active = true
  }

  return { profiles: Array.from(profiles.values()), activeProfile }
}
