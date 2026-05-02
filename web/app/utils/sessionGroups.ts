import type { WebChatSession, WebChatWorkspace } from '../types/web-chat'

export type SessionGroup = {
  id: string
  label: string
  path: string | null
  sessions: WebChatSession[]
  active: boolean
  workspace?: WebChatWorkspace
}

type BuildSessionGroupsOptions = {
  sessions: WebChatSession[]
  workspaces: WebChatWorkspace[]
  selectedWorkspace: string | null
}

const OTHER_WORKSPACE_KEY = '__other__'
const ARCHIVED_WORKSPACE_KEY = '__archived__'

export function workspaceKey(workspace: string | null): string {
  return workspace || OTHER_WORKSPACE_KEY
}

export function buildSessionGroups(options: BuildSessionGroupsOptions): SessionGroup[] {
  const archivedSessions = options.sessions.filter(session => session.archived)
  const visibleSessions = options.sessions.filter(session => !session.archived)
  const sessionsByWorkspace = new Map<string, WebChatSession[]>()
  for (const session of visibleSessions) {
    const key = workspaceKey(session.workspace)
    sessionsByWorkspace.set(key, [...(sessionsByWorkspace.get(key) || []), session])
  }

  const groups: SessionGroup[] = [...options.workspaces]
    .map((workspace) => {
      const key = workspaceKey(workspace.path)
      return {
        id: key,
        label: workspace.label,
        path: workspace.path,
        sessions: sortedSessions(sessionsByWorkspace.get(key) || []),
        active: workspace.active || options.selectedWorkspace === workspace.path,
        workspace
      }
    })

  const knownKeys = new Set(groups.map(group => group.id))
  const otherSessions = Array.from(sessionsByWorkspace.entries())
    .filter(([key]) => key === OTHER_WORKSPACE_KEY || !knownKeys.has(key))
    .flatMap(([, workspaceSessions]) => workspaceSessions)

  if (otherSessions.length) {
    groups.push({
      id: OTHER_WORKSPACE_KEY,
      label: 'Other chats',
      path: null,
      sessions: sortedSessions(otherSessions),
      active: false
    })
  }

  if (archivedSessions.length) {
    groups.push({
      id: ARCHIVED_WORKSPACE_KEY,
      label: 'Archived',
      path: null,
      sessions: sortedSessions(archivedSessions),
      active: false
    })
  }

  return groups
}

function sortedSessions(sessions: WebChatSession[]): WebChatSession[] {
  return [...sessions].sort(compareSessionsByLastMessage)
}

function compareSessionsByLastMessage(a: WebChatSession, b: WebChatSession): number {
  return Number(b.pinned) - Number(a.pinned)
    || timestampValue(b.updatedAt) - timestampValue(a.updatedAt)
    || timestampValue(b.createdAt) - timestampValue(a.createdAt)
    || a.id.localeCompare(b.id)
}

function timestampValue(value: string): number {
  const timestamp = new Date(value).getTime()
  return Number.isFinite(timestamp) ? timestamp : 0
}
