import { readFile, readdir } from 'node:fs/promises'
import { dirname, join } from 'node:path'

export type HermesSessionFile = {
  session_id?: string
  messages?: HermesSessionMessage[]
}

export type HermesSessionMessage = {
  role?: string
  content?: unknown
  reasoning?: unknown
  reasoning_content?: unknown
  codex_reasoning_items?: unknown
}

export type HermesSessionRuntimeConfig = {
  hermesHome?: string
  hermesAcpArgs?: string[]
  hermesAcpCwd?: string
}

export async function readHermesSession(config: HermesSessionRuntimeConfig, sessionId: string): Promise<HermesSessionFile | null> {
  for (const sessionsDir of hermesSessionsDirs(config)) {
    const directPath = join(sessionsDir, `session_${sessionId}.json`)
    const direct = await readSessionFile(directPath)
    if (direct) return direct

    try {
      const entries = await readdir(sessionsDir, { withFileTypes: true })
      for (const entry of entries) {
        if (!entry.isFile() || !entry.name.endsWith('.json')) continue
        const session = await readSessionFile(join(sessionsDir, entry.name))
        if (session?.session_id === sessionId) return session
      }
    } catch {
      continue
    }
  }

  return null
}

async function readSessionFile(path: string): Promise<HermesSessionFile | null> {
  try {
    const parsed = JSON.parse(await readFile(path, 'utf8')) as HermesSessionFile
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch {
    return null
  }
}

function hermesSessionsDirs(config: HermesSessionRuntimeConfig) {
  return unique([
    config.hermesHome,
    process.env.HERMES_HOME,
    hermesHomeFromProfile(config.hermesAcpArgs),
    hermesProfileHomeFromNestedHome()
  ].filter(Boolean).map(home => join(home, 'sessions')))
}

function hermesHomeFromProfile(args?: string[]) {
  const profile = profileFromArgs(args)
  if (!profile || !process.env.HOME) return null
  return join(process.env.HOME, '.hermes', 'profiles', profile)
}

function profileFromArgs(args?: string[]) {
  if (!args?.length) return null
  const index = args.indexOf('--profile')
  const profile = index >= 0 ? args[index + 1] : null
  return profile || null
}

function hermesProfileHomeFromNestedHome() {
  const home = process.env.HOME
  if (!home?.endsWith('/home')) return null
  const profileHome = dirname(home)
  return profileHome.includes('/.hermes/profiles/') ? profileHome : null
}

function unique(values: string[]) {
  return Array.from(new Set(values))
}
