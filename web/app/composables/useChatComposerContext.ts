import type { AppWorkspace, ChatPromptAttachment } from '~/types/chat'
import { resolveSelectedWorkspace } from '~/utils/workspaceSelection'

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
  const api = useAppWorkspacesApi()

  const workspaces = useState<AppWorkspace[]>('chat-composer-workspaces', () => [])
  const attachments = useState<ChatPromptAttachment[]>('chat-composer-attachments', () => [])
  const selectedWorkspace = useState<string | null>('chat-composer-selected-workspace', () => null)
  const workspacesLoading = useState('chat-composer-workspaces-loading', () => false)
  const attachmentsLoading = useState('chat-composer-attachments-loading', () => false)
  const contextError = useState<Error | undefined>('chat-composer-context-error', () => undefined)

  function reconcileWorkspace(preferredWorkspace?: string | null) {
    selectedWorkspace.value = resolveSelectedWorkspace({
      workspaces: workspaces.value,
      preferredWorkspace,
      persistedWorkspace: storedValue(SELECTED_WORKSPACE_KEY),
      currentWorkspace: selectedWorkspace.value
    })
  }

  async function loadWorkspaces(preferredWorkspace?: string | null) {
    workspacesLoading.value = true
    try {
      const response = await api.getWorkspaces()
      workspaces.value = Array.isArray(response.workspaces) ? response.workspaces : []
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

  function selectWorkspace(path: string | null) {
    if (path !== selectedWorkspace.value) {
      attachments.value = []
    }
    selectedWorkspace.value = path
    rememberValue(SELECTED_WORKSPACE_KEY, path)
  }

  async function uploadFiles(files: File[]) {
    attachmentsLoading.value = true
    try {
      const nextAttachments = await filesToPromptAttachments(files)
      attachments.value = [...attachments.value, ...nextAttachments]
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Could not attach files.')
      contextError.value = error
      throw error
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
    loadWorkspaces,
    selectWorkspace,
    uploadFiles,
    removeAttachment,
    clearAttachments
  }
}
