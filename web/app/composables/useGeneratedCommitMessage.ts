import { onBeforeUnmount, ref, type Ref } from 'vue'
import type { GitFileSelection } from '~/types/web-chat'
import { writeClipboardText } from '~/utils/clipboard'

export type GeneratedCommitMessageOptions = {
  api: ReturnType<typeof useHermesApi>
  sessionId: Readonly<Ref<string>>
  selectedWorkspace: Readonly<Ref<string | null | undefined>>
  toast: ReturnType<typeof useToast>
  showError: (err: unknown, fallback: string) => void
}

export function useGeneratedCommitMessage(options: GeneratedCommitMessageOptions) {
  const generating = ref(false)
  const message = ref('')
  const modalOpen = ref(false)
  const copied = ref(false)
  let copiedTimer: ReturnType<typeof setTimeout> | undefined

  function clearCopiedTimer() {
    if (!copiedTimer) return
    clearTimeout(copiedTimer)
    copiedTimer = undefined
  }

  function showCopied() {
    copied.value = true
    clearCopiedTimer()
    copiedTimer = setTimeout(() => {
      copied.value = false
      copiedTimer = undefined
    }, 2500)
  }

  async function copy() {
    if (!message.value) return

    try {
      await writeClipboardText(message.value)
      showCopied()
    } catch (err) {
      options.toast.add({
        color: 'error',
        title: 'Could not copy commit message',
        description: err instanceof Error ? err.message : String(err)
      })
    }
  }

  async function generate() {
    const workspace = options.selectedWorkspace.value
    if (!workspace || generating.value) return

    generating.value = true
    message.value = ''
    copied.value = false
    clearCopiedTimer()

    try {
      const status = await options.api.getGitStatus(workspace)
      const selection: GitFileSelection[] = status.files.map(file => ({ area: file.area, path: file.path }))
      if (!selection.length) {
        options.toast.add({ color: 'warning', title: 'No Git changes', description: 'There are no changed files to generate a commit message from.' })
        return
      }

      const suggestion = await options.api.generateCommitMessage({
        workspace,
        sessionId: options.sessionId.value,
        selection
      })
      message.value = [suggestion.subject, suggestion.body].filter(Boolean).join('\n\n')
      modalOpen.value = true
    } catch (err) {
      options.showError(err, 'Could not generate commit message')
    } finally {
      generating.value = false
    }
  }

  onBeforeUnmount(clearCopiedTimer)

  return {
    generating,
    message,
    modalOpen,
    copied,
    generate,
    copy
  }
}
