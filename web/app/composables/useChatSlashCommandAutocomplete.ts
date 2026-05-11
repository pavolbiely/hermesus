import type { Ref } from 'vue'
import type { SlashCommand } from '~/types/chat'

type SlashAutocompleteState = {
  isOpen: Ref<boolean>
  highlightedIndex: Ref<number>
  close: () => void
  moveHighlight: (delta: number) => void
  highlightedCommand: () => SlashCommand | null
}

type UseChatSlashCommandAutocompleteOptions = {
  input: Ref<string>
  slashCommands: SlashAutocompleteState
}

export function useChatSlashCommandAutocomplete(options: UseChatSlashCommandAutocompleteOptions) {
  function selectSlashCommand(command: SlashCommand) {
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
    if (event.shiftKey || event.isComposing) return
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
