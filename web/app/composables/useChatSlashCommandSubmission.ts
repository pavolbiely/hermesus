import { nextTick } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import type { WebChatCommand, WebChatMessage } from '~/types/web-chat'
import { requiresWorkspaceBeforeSubmit } from '~/utils/slashCommands'

type UseChatSlashCommandSubmissionOptions = {
  api: ReturnType<typeof useHermesApi>
  input: Ref<string>
  messages: Ref<WebChatMessage[]>
  sessionId: ComputedRef<string>
  selectedWorkspace: Ref<string | null>
  selectedModel: Ref<string | null>
  selectedReasoningEffort: Ref<string | null>
  streamError: Ref<Error | undefined>
  workspaceInvalidSignal: Ref<number>
  slashCommands: ReturnType<typeof useSlashCommands>
  toast: ReturnType<typeof useToast>
  submitStatus: Ref<'ready' | 'submitted' | 'streaming' | 'error'>
}

export function useChatSlashCommandSubmission(options: UseChatSlashCommandSubmissionOptions) {
  const commandSubmitting = ref(false)

  function showCommandError(err: unknown, commandText: string) {
    const message = getHermesErrorMessage(err, 'Command failed')
    options.toast.add({ color: 'warning', title: commandText, description: message })
  }

  function appendCommandResponse(commandText: string, response: Awaited<ReturnType<typeof options.api.executeCommand>>) {
    options.messages.value.push({
      id: `command-user-${Date.now()}`,
      role: 'user',
      createdAt: new Date().toISOString(),
      parts: [{ type: 'text', text: commandText }]
    })
    if (response.message) {
      if (response.changes) response.message.parts.push({ type: 'changes', changes: response.changes })
      options.messages.value.push(response.message)
    }
  }

  function shouldBlockForMissingWorkspace(message: string) {
    if (!requiresWorkspaceBeforeSubmit(message, options.selectedWorkspace.value)) return false
    options.workspaceInvalidSignal.value += 1
    return true
  }

  async function executeSlashCommand(commandText: string) {
    if (commandSubmitting.value) return true
    if (shouldBlockForMissingWorkspace(commandText)) return false

    commandSubmitting.value = true
    options.submitStatus.value = 'submitted'
    options.streamError.value = undefined
    try {
      const response = await options.api.executeCommand({
        command: commandText,
        sessionId: options.sessionId.value,
        workspace: options.selectedWorkspace.value,
        model: options.selectedModel.value,
        reasoningEffort: options.selectedReasoningEffort.value
      })
      appendCommandResponse(commandText, response)
    } catch (err) {
      showCommandError(err, commandText)
    } finally {
      await nextTick()
      options.submitStatus.value = 'ready'
      commandSubmitting.value = false
    }
    return true
  }

  async function submitSlashCommandIfNeeded(message: string) {
    if (!message.startsWith('/')) return false
    await options.slashCommands.loadCommands()
    const command = options.slashCommands.exactCommand(message)
    if (!command) return false
    const executed = await executeSlashCommand(command.name)
    if (executed) options.input.value = ''
    return true
  }

  async function selectSlashCommand(command: WebChatCommand) {
    options.input.value = command.name
    const executed = await executeSlashCommand(command.name)
    if (executed) options.input.value = ''
  }

  function onPromptArrowDown(event: KeyboardEvent) {
    if (!options.slashCommands.isOpen.value) return
    event.preventDefault()
    options.slashCommands.moveHighlight(1)
  }

  function onPromptArrowUp(event: KeyboardEvent) {
    if (!options.slashCommands.isOpen.value) return
    event.preventDefault()
    options.slashCommands.moveHighlight(-1)
  }

  function onPromptEscape(event: KeyboardEvent) {
    if (!options.slashCommands.isOpen.value) return
    event.preventDefault()
    event.stopPropagation()
    options.slashCommands.close()
  }

  function onPromptEnter(event: KeyboardEvent) {
    if (!options.slashCommands.isOpen.value) return
    const command = options.slashCommands.highlightedCommand()
    if (!command) return
    event.preventDefault()
    event.stopPropagation()
    void selectSlashCommand(command)
  }

  return {
    shouldBlockForMissingWorkspace,
    submitSlashCommandIfNeeded,
    selectSlashCommand,
    onPromptArrowDown,
    onPromptArrowUp,
    onPromptEscape,
    onPromptEnter
  }
}
