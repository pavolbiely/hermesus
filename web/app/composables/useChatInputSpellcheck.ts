import type { SpellcheckLanguage } from '~/utils/spellcheckPreferences'
import {
  chatInputSpellcheckEnabled,
  chatInputSpellcheckLanguage,
  setChatInputSpellcheckEnabled,
  setChatInputSpellcheckLanguage,
  spellcheckHtmlLang
} from '~/utils/spellcheckPreferences'

export function useChatInputSpellcheck() {
  const enabled = useState('chat-input-spellcheck-enabled', () => chatInputSpellcheckEnabled())
  const language = useState<SpellcheckLanguage>('chat-input-spellcheck-language', () => chatInputSpellcheckLanguage())

  onMounted(() => {
    enabled.value = chatInputSpellcheckEnabled()
    language.value = chatInputSpellcheckLanguage()
  })

  const spellcheck = computed(() => enabled.value)
  const lang = computed(() => spellcheckHtmlLang(language.value))

  function updateEnabled(value: boolean) {
    enabled.value = value
    setChatInputSpellcheckEnabled(value)
  }

  function updateLanguage(value: SpellcheckLanguage) {
    language.value = value
    setChatInputSpellcheckLanguage(value)
  }

  return {
    enabled,
    language,
    spellcheck,
    lang,
    updateEnabled,
    updateLanguage
  }
}
