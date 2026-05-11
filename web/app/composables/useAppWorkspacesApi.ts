import type {
  AppWorkspaceResponse,
  AppWorkspacesResponse,
  DirectorySuggestionsResponse,
  DeleteResponse,
  FilePreviewRequest,
  FilePreviewResolveRequest,
  FilePreviewResolveResponse,
  HermesProfilesResponse,
  ReorderWorkspacesRequest,
  SaveWorkspaceRequest,
  AppFilePreview
} from '~/types/chat'

export function useAppWorkspacesApi() {
  return {
    getProfiles: () => $fetch<HermesProfilesResponse>('/api/app/profiles'),
    getWorkspaces: () => $fetch<AppWorkspacesResponse>('/api/app/workspaces'),
    getWorkspaceDirectories: (prefix: string) => $fetch<DirectorySuggestionsResponse>('/api/app/workspaces/directories', {
      query: { prefix }
    }),
    fetchFilePreview: (payload: FilePreviewRequest) => $fetch<AppFilePreview>('/api/app/file-preview', {
      method: 'POST',
      body: payload
    }),
    resolveFilePreviewPaths: (payload: FilePreviewResolveRequest) => $fetch<FilePreviewResolveResponse>('/api/app/file-preview/resolve', {
      method: 'POST',
      body: payload
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
