interface WorkspaceOption {
  path: string
}

export interface ResolveSelectedWorkspaceOptions {
  workspaces: WorkspaceOption[]
  preferredWorkspace?: string | null
  persistedWorkspace: string | null
  currentWorkspace: string | null
}

export function resolveSelectedWorkspace({
  workspaces,
  preferredWorkspace,
  persistedWorkspace,
  currentWorkspace
}: ResolveSelectedWorkspaceOptions) {
  return workspaces.find(workspace => workspace.path === preferredWorkspace)?.path
    || workspaces.find(workspace => workspace.path === currentWorkspace)?.path
    || workspaces.find(workspace => workspace.path === persistedWorkspace)?.path
    || null
}
