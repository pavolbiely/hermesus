import type { WebChatAttachment, WebChatSession, WebChatWorkspace } from '~/types/web-chat'

const SELECTED_WORKSPACE_KEY = 'hermes-chat-selected-workspace'

function storedValue(key: string) {
  if (import.meta.server) return null
  return localStorage.getItem(key)
}

function rememberValue(key: string, value: string | null) {
  if (import.meta.server) return
  if (value) localStorage.setItem(key, value)
  else localStorage.removeItem(key)
}

export function useChatComposerContext() {
  const api = useHermesApi()

  const workspaces = useState<WebChatWorkspace[]>('chat-composer-workspaces', () => [])
  const attachments = useState<WebChatAttachment[]>('chat-composer-attachments', () => [])
  const selectedWorkspace = useState<string | null>('chat-composer-selected-workspace', () => null)
  const workspacesLoading = useState('chat-composer-workspaces-loading', () => false)
  const attachmentsLoading = useState('chat-composer-attachments-loading', () => false)
  const contextError = useState<Error | undefined>('chat-composer-context-error', () => undefined)

  function reconcileWorkspace(preferredWorkspace?: string | null) {
    const preferred = workspaces.value.find(workspace => workspace.path === preferredWorkspace)?.path
    const persisted = storedValue(SELECTED_WORKSPACE_KEY)
    const selected = preferred
      || workspaces.value.find(workspace => workspace.path === persisted)?.path
      || workspaces.value.find(workspace => workspace.path === selectedWorkspace.value)?.path
      || null
    selectedWorkspace.value = selected
  }

  async function loadWorkspaces(preferredWorkspace?: string | null) {
    workspacesLoading.value = true
    try {
      const response = await api.getWorkspaces()
      workspaces.value = response.workspaces
      reconcileWorkspace(preferredWorkspace)
    } catch (err) {
      contextError.value = new Error(getHermesErrorMessage(err, 'Could not load workspaces.'))
    } finally {
      workspacesLoading.value = false
    }
  }

  async function initialize() {
    if (workspaces.value.length || workspacesLoading.value) return
    await loadWorkspaces()
  }

  async function initializeForSession(session: WebChatSession) {
    if (workspaces.value.length) {
      reconcileWorkspace(session.workspace)
      return
    }
    await loadWorkspaces(session.workspace)
  }

  function selectWorkspace(path: string | null) {
    if (path !== selectedWorkspace.value) {
      attachments.value = []
    }
    selectedWorkspace.value = path
    rememberValue(SELECTED_WORKSPACE_KEY, path)
  }

  async function uploadFiles(files: File[]) {
    if (!files.length) return
    if (!selectedWorkspace.value) {
      const error = new Error('Select a workspace before attaching files.')
      contextError.value = error
      throw error
    }
    attachmentsLoading.value = true
    contextError.value = undefined
    try {
      const response = await api.uploadAttachments(files, selectedWorkspace.value)
      attachments.value = [...attachments.value, ...response.attachments]
    } catch (err) {
      contextError.value = new Error(getHermesErrorMessage(err, 'Could not upload attachment.'))
      throw contextError.value
    } finally {
      attachmentsLoading.value = false
    }
  }

  function removeAttachment(id: string) {
    attachments.value = attachments.value.filter(attachment => attachment.id !== id)
  }

  function clearAttachments() {
    attachments.value = []
  }

  return {
    workspaces,
    attachments,
    selectedWorkspace,
    workspacesLoading,
    attachmentsLoading,
    contextError,
    initialize,
    initializeForSession,
    loadWorkspaces,
    selectWorkspace,
    uploadFiles,
    removeAttachment,
    clearAttachments
  }
}
