import type { Ref } from 'vue'
import type { WebChatCommand } from '~/types/web-chat'

type UseChatSlashCommandAutocompleteOptions = {
  input: Ref<string>
  slashCommands: ReturnType<typeof useSlashCommands>
}

export function useChatSlashCommandAutocomplete(options: UseChatSlashCommandAutocompleteOptions) {
  function selectSlashCommand(command: WebChatCommand) {
    options.input.value = command.name
    options.slashCommands.close()
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
    selectSlashCommand(command)
  }

  return {
    selectSlashCommand,
    onPromptArrowDown,
    onPromptArrowUp,
    onPromptEscape,
    onPromptEnter
  }
}
