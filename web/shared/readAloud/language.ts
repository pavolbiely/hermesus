export type ReadAloudLanguage = 'sk' | 'cs' | 'en' | 'de' | 'es' | 'fr' | 'it' | 'pl' | 'pt' | 'uk'

const defaultLanguage: ReadAloudLanguage = 'en'

const languageHints: Array<{ language: ReadAloudLanguage, score: RegExp[] }> = [
  {
    language: 'sk',
    score: [
      /[ľĺŕôä]/i,
      /\b(že|som|si|sme|ste|nie|áno|keď|čo|mám|máme|prečo|ďakujem|prosím|správa|odpoveď|nastavenie|jazyk)\b/i
    ]
  },
  {
    language: 'cs',
    score: [
      /[ěůř]/i,
      /\b(že|jsem|jsi|jsme|jste|není|ano|když|co|mám|máme|proč|děkuji|prosím|zpráva|odpověď|nastavení|jazyk)\b/i
    ]
  },
  {
    language: 'de',
    score: [
      /[ß]/i,
      /\b(und|oder|nicht|ich|du|wir|sie|danke|bitte|antwort|nachricht|einstellung|sprache)\b/i
    ]
  },
  {
    language: 'es',
    score: [
      /[¿¡ñ]/i,
      /\b(que|una|para|con|gracias|por favor|mensaje|respuesta|ajuste|idioma)\b/i
    ]
  },
  {
    language: 'fr',
    score: [
      /[àâçéèêëîïôùûüÿœ]/i,
      /\b(que|une|pour|avec|merci|s'il vous plaît|message|réponse|paramètre|langue)\b/i
    ]
  },
  {
    language: 'it',
    score: [
      /\b(che|una|per|con|grazie|per favore|messaggio|risposta|impostazione|lingua)\b/i
    ]
  },
  {
    language: 'pl',
    score: [
      /[ąćęłńóśźż]/i,
      /\b(że|jestem|nie|tak|kiedy|dziękuję|proszę|wiadomość|odpowiedź|ustawienie|język)\b/i
    ]
  },
  {
    language: 'pt',
    score: [
      /[ãõ]/i,
      /\b(que|uma|para|com|obrigado|obrigada|por favor|mensagem|resposta|configuração|idioma)\b/i
    ]
  },
  {
    language: 'uk',
    score: [
      /[іїєґ]/i,
      /\b(що|так|ні|дякую|будь ласка|повідомлення|відповідь|налаштування|мова)\b/i
    ]
  }
]

export function detectReadAloudLanguage(text: string): ReadAloudLanguage {
  const normalized = text.trim()
  if (!normalized) return defaultLanguage

  const scored = languageHints
    .map(({ language, score }) => ({
      language,
      score: score.reduce((total, pattern) => total + (pattern.test(normalized) ? 1 : 0), 0)
    }))
    .filter(item => item.score > 0)
    .sort((a, b) => b.score - a.score)

  return scored[0]?.language ?? defaultLanguage
}

export function readAloudLanguageLocale(language: ReadAloudLanguage) {
  return {
    sk: 'sk-SK',
    cs: 'cs-CZ',
    en: 'en-US',
    de: 'de-DE',
    es: 'es-ES',
    fr: 'fr-FR',
    it: 'it-IT',
    pl: 'pl-PL',
    pt: 'pt-PT',
    uk: 'uk-UA'
  }[language]
}

export function edgeReadAloudVoice(language: ReadAloudLanguage) {
  return {
    sk: 'sk-SK-LukasNeural',
    cs: 'cs-CZ-AntoninNeural',
    en: 'en-US-BrianNeural',
    de: 'de-DE-ConradNeural',
    es: 'es-ES-AlvaroNeural',
    fr: 'fr-FR-HenriNeural',
    it: 'it-IT-DiegoNeural',
    pl: 'pl-PL-MarekNeural',
    pt: 'pt-PT-DuarteNeural',
    uk: 'uk-UA-OstapNeural'
  }[language]
}
