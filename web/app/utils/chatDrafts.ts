const DRAFT_STORAGE_PREFIX = 'hermesum:web-chat:draft:v1:'

export const NEW_CHAT_DRAFT_ID = 'new-chat'

export function chatDraftStorageKey(draftId: string) {
  return `${DRAFT_STORAGE_PREFIX}${encodeURIComponent(draftId)}`
}

export function readChatDraft(storage: Storage | undefined, draftId: string) {
  if (!storage) return ''

  try {
    return storage.getItem(chatDraftStorageKey(draftId)) || ''
  } catch {
    return ''
  }
}

export function writeChatDraft(storage: Storage | undefined, draftId: string, text: string) {
  if (!storage) return

  try {
    const key = chatDraftStorageKey(draftId)
    if (text) storage.setItem(key, text)
    else storage.removeItem(key)
  } catch {
    // Draft persistence is best-effort; quota/private-mode failures should not block chat input.
  }
}
