export type SpellcheckLanguage = 'browser' | 'en-US' | 'sk-SK' | 'cs-CZ' | 'de-DE'

export type SpellcheckLanguageItem = {
  label: string
  value: SpellcheckLanguage
  description: string
}

const enabledPreferenceKey = 'hermes.chatInput.spellcheck.enabled'
const languagePreferenceKey = 'hermes.chatInput.spellcheck.language'
const defaultEnabled = true
const defaultLanguage: SpellcheckLanguage = 'browser'

export const spellcheckLanguageItems = [
  {
    label: 'Browser default',
    value: 'browser',
    description: 'Let the browser use its current spellcheck dictionary.'
  },
  {
    label: 'English',
    value: 'en-US',
    description: 'Use the English browser dictionary when installed.'
  },
  {
    label: 'Slovak',
    value: 'sk-SK',
    description: 'Use the Slovak browser dictionary when installed.'
  },
  {
    label: 'Czech',
    value: 'cs-CZ',
    description: 'Use the Czech browser dictionary when installed.'
  },
  {
    label: 'German',
    value: 'de-DE',
    description: 'Use the German browser dictionary when installed.'
  }
] satisfies SpellcheckLanguageItem[]

function isClient() {
  return typeof window !== 'undefined'
}

function storedPreference(key: string) {
  if (!isClient()) return null

  try {
    const value = window.localStorage.getItem(key)?.trim()
    return value || null
  } catch {
    return null
  }
}

function setStoredPreference(key: string, value: string | null) {
  if (!isClient()) return

  try {
    const normalized = value?.trim()
    if (normalized) {
      window.localStorage.setItem(key, normalized)
      return
    }
    window.localStorage.removeItem(key)
  } catch {
    // Local preferences are best-effort only.
  }
}

function isSpellcheckLanguage(value: string | null): value is SpellcheckLanguage {
  return spellcheckLanguageItems.some(item => item.value === value)
}

export function chatInputSpellcheckEnabled() {
  const stored = storedPreference(enabledPreferenceKey)
  if (stored === null) return defaultEnabled
  return stored === 'true'
}

export function setChatInputSpellcheckEnabled(enabled: boolean) {
  setStoredPreference(enabledPreferenceKey, enabled === defaultEnabled ? null : String(enabled))
}

export function chatInputSpellcheckLanguage(): SpellcheckLanguage {
  const stored = storedPreference(languagePreferenceKey)
  return isSpellcheckLanguage(stored) ? stored : defaultLanguage
}

export function setChatInputSpellcheckLanguage(language: SpellcheckLanguage) {
  setStoredPreference(languagePreferenceKey, language === defaultLanguage ? null : language)
}

export function spellcheckHtmlLang(language: SpellcheckLanguage) {
  return language === 'browser' ? undefined : language
}
