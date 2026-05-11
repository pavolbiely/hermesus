import type {
  AppWorkspaceResponse,
  AppWorkspacesResponse,
  DirectorySuggestionsResponse,
  DeleteResponse,
  ReorderWorkspacesRequest,
  SaveWorkspaceRequest
} from '~/types/chat'

export function useAppWorkspacesApi() {
  return {
    getWorkspaces: () => $fetch<AppWorkspacesResponse>('/api/app/workspaces'),
    getWorkspaceDirectories: (prefix: string) => $fetch<DirectorySuggestionsResponse>('/api/app/workspaces/directories', {
      query: { prefix }
    }),
    createWorkspace: (payload: SaveWorkspaceRequest) => $fetch<AppWorkspaceResponse>('/api/app/workspaces', {
      method: 'POST',
      body: payload
    }),
    updateWorkspace: (id: string, payload: SaveWorkspaceRequest) => $fetch<AppWorkspaceResponse>(`/api/app/workspaces/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: payload
    }),
    reorderWorkspaces: (payload: ReorderWorkspacesRequest) => $fetch<AppWorkspacesResponse>('/api/app/workspaces/order', {
      method: 'PATCH',
      body: payload
    }),
    deleteWorkspace: (id: string) => $fetch<DeleteResponse>(`/api/app/workspaces/${encodeURIComponent(id)}`, {
      method: 'DELETE'
    })
  }
}
