import type { Ref } from 'vue'
import type { SlashCommand } from '~/types/chat'
import {
  exactSlashCommandMatch,
  filterSlashCommands,
  nextSlashCommandDismissedState
} from '~/utils/slashCommands'

type StaticSlashCommandOptions = {
  input: Ref<string>
  commands: Ref<SlashCommand[]>
}

export function useStaticSlashCommands(options: StaticSlashCommandOptions) {
  const loading = ref(false)
  const highlightedIndex = ref(0)
  const dismissed = ref(false)

  const query = computed(() => {
    const value = options.input.value
    if (!value.startsWith('/')) return null
    if (/\s/.test(value)) return null
    return value.slice(1).toLowerCase()
  })

  const filteredCommands = computed(() => filterSlashCommands(options.commands.value, options.input.value))
  const isOpen = computed(() => query.value !== null && !dismissed.value && filteredCommands.value.length > 0)

  watch(() => options.input.value, (value, previousValue) => {
    dismissed.value = nextSlashCommandDismissedState(previousValue, value, dismissed.value)
  }, { immediate: true })

  watch(filteredCommands, () => {
    highlightedIndex.value = 0
  })

  function moveHighlight(delta: number) {
    const count = filteredCommands.value.length
    if (!count) return
    highlightedIndex.value = (highlightedIndex.value + delta + count) % count
  }

  function highlightedCommand() {
    return filteredCommands.value[highlightedIndex.value] || null
  }

  function exactCommand(input: string) {
    return exactSlashCommandMatch(options.commands.value, input)
  }

  function close() {
    dismissed.value = true
    highlightedIndex.value = 0
  }

  return {
    commands: options.commands,
    loading,
    query,
    isOpen,
    filteredCommands,
    highlightedIndex,
    highlightedCommand,
    exactCommand,
    moveHighlight,
    close
  }
}
