import { execFile } from 'node:child_process'
import { homedir } from 'node:os'
import { dirname, join } from 'node:path'
import { promisify } from 'node:util'

const execFileAsync = promisify(execFile)

type RuntimeConfig = {
  hermesAcpArgs?: string[] | string
}

type SessionRow = {
  id: string
  title: string | null
  parent_session_id: string | null
  started_at: number
  ended_at: number | null
  end_reason: string | null
}

export type AcpSessionLineageInfo = {
  rootSessionId: string
  rootTitle: string | null
}

function hermesProfile(config: RuntimeConfig) {
  const args = Array.isArray(config.hermesAcpArgs)
    ? config.hermesAcpArgs
    : typeof config.hermesAcpArgs === 'string'
      ? config.hermesAcpArgs.split(' ').filter(Boolean)
      : []

  const profileFlagIndex = args.findIndex(arg => arg === '--profile' || arg === '-p')
  if (profileFlagIndex >= 0) return args[profileFlagIndex + 1] || null

  const inlineProfile = args.find(arg => arg.startsWith('--profile='))
  if (inlineProfile) return inlineProfile.slice('--profile='.length) || null

  return process.env.HERMESUM_PROFILE || null
}

function profileStateDbPath(profile: string) {
  const home = homedir()
  const profileHomeSuffix = join('.hermes', 'profiles', profile, 'home')
  if (home.endsWith(profileHomeSuffix)) return join(dirname(home), 'state.db')
  return join(home, '.hermes', 'profiles', profile, 'state.db')
}

function isCompressionContinuation(child: SessionRow, parent: SessionRow) {
  return parent.end_reason === 'compression'
    && typeof parent.ended_at === 'number'
    && typeof child.started_at === 'number'
    && child.started_at >= parent.ended_at
}

function lineageRoot(row: SessionRow, rowsById: Map<string, SessionRow>) {
  let current = row
  const seen = new Set<string>()

  while (current.parent_session_id && !seen.has(current.id)) {
    seen.add(current.id)
    const parent = rowsById.get(current.parent_session_id)
    if (!parent || !isCompressionContinuation(current, parent)) break
    current = parent
  }

  return current
}

export async function listAcpSessionLineage(config: RuntimeConfig): Promise<Record<string, AcpSessionLineageInfo>> {
  const profile = hermesProfile(config)
  if (!profile) return {}

  const dbPath = profileStateDbPath(profile)
  let stdout = ''
  try {
    const result = await execFileAsync('python3', [
      '-c',
      `import json, sqlite3, sys
con = sqlite3.connect(sys.argv[1])
con.row_factory = sqlite3.Row
rows = con.execute('select id,title,parent_session_id,started_at,ended_at,end_reason from sessions').fetchall()
print(json.dumps([dict(row) for row in rows]))`,
      dbPath
    ], { maxBuffer: 10 * 1024 * 1024 })
    stdout = result.stdout
  } catch {
    return {}
  }

  let rows: SessionRow[]
  try {
    rows = JSON.parse(stdout || '[]') as SessionRow[]
  } catch {
    return {}
  }

  const rowsById = new Map(rows.map(row => [row.id, row]))
  return Object.fromEntries(rows.map((row) => {
    const root = lineageRoot(row, rowsById)
    return [row.id, {
      rootSessionId: root.id,
      rootTitle: root.title
    }]
  }))
}
