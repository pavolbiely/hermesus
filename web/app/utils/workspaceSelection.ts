interface WorkspaceOption {
  label?: string
  path: string
}

export type WorkspaceSelectItem = {
  label: string
  value: string
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

export function workspaceSelectItems(workspaces: WorkspaceOption[], selectedWorkspace: string | null): WorkspaceSelectItem[] {
  const items = workspaces.map(workspace => ({
    label: workspace.label || workspace.path,
    value: workspace.path
  }))

  if (!selectedWorkspace || items.some(item => item.value === selectedWorkspace)) return items

  return [
    ...items,
    { label: selectedWorkspace, value: selectedWorkspace }
  ]
}
