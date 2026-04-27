type SlashCommandLike = {
  name: string
  description?: string
}

function slashCommandQuery(input: string) {
  const value = input.trim()
  if (!value.startsWith('/')) return null
  if (/\s/.test(value)) return null
  return value.slice(1).toLowerCase()
}

function isSlashCommandQueryInput(input: string | null | undefined) {
  return input !== null && input !== undefined && slashCommandQuery(input) !== null
}

export function filterSlashCommands<T extends SlashCommandLike>(commands: T[], input: string): T[] {
  const query = slashCommandQuery(input)
  if (query === null) return []

  return commands.filter((command) => {
    const name = command.name.slice(1).toLowerCase()
    const description = command.description?.toLowerCase() || ''
    return name.startsWith(query) || description.includes(query)
  })
}

export function exactSlashCommandMatch<T extends SlashCommandLike>(commands: T[], input: string): T | null {
  const value = input.trim()
  if (!value.startsWith('/') || /\s/.test(value)) return null
  const normalized = value.toLowerCase()
  return commands.find(command => command.name.toLowerCase() === normalized) || null
}

export function nextSlashCommandDismissedState(
  previousInput: string | null | undefined,
  currentInput: string,
  dismissed: boolean
): boolean {
  if (!isSlashCommandQueryInput(currentInput)) return false
  if (!isSlashCommandQueryInput(previousInput)) return false
  return dismissed
}
