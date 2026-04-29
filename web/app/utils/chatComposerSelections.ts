export type ChatComposerSelection = {
  model: string | null
  provider: string | null
  reasoningEffort: string | null
}

export type ChatComposerSession = {
  model?: string | null
  provider?: string | null
  reasoningEffort?: string | null
}

function normalizeValue(value: string | null | undefined) {
  const normalized = value?.trim()
  return normalized || null
}

function normalizeReasoning(value: string | null | undefined) {
  return normalizeValue(value)?.toLowerCase() || null
}

export function normalizeChatComposerSelection(selection: Partial<ChatComposerSelection>): ChatComposerSelection {
  return {
    model: normalizeValue(selection.model),
    provider: normalizeValue(selection.provider),
    reasoningEffort: normalizeReasoning(selection.reasoningEffort)
  }
}

export function rememberChatComposerSelection(
  selections: Record<string, ChatComposerSelection>,
  sessionId: string | null | undefined,
  selection: Partial<ChatComposerSelection>
) {
  const normalizedSessionId = normalizeValue(sessionId)
  if (!normalizedSessionId) return selections

  const normalizedSelection = normalizeChatComposerSelection(selection)
  return {
    ...selections,
    [normalizedSessionId]: normalizedSelection
  }
}

export function resolveSessionComposerSelection(
  session: ChatComposerSession | null | undefined,
  savedSelection?: Partial<ChatComposerSelection> | null
): ChatComposerSelection {
  const saved = savedSelection ? normalizeChatComposerSelection(savedSelection) : null
  const persisted = normalizeChatComposerSelection({
    model: session?.model,
    provider: session?.provider,
    reasoningEffort: session?.reasoningEffort
  })

  return {
    model: saved?.model || persisted.model,
    provider: saved?.provider || persisted.provider,
    reasoningEffort: saved?.reasoningEffort || persisted.reasoningEffort
  }
}
