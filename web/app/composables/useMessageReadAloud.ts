import type { WebChatMessage } from '~/types/web-chat'
import { messageSpeechText } from '~/utils/chatMessages'
import {
  readAloudContentMode,
  readAloudEngine,
  readAloudSpeed,
  readAloudWebSpeechVoiceURI
} from '~/utils/readAloudPreferences'

type ReadAloudStatus = 'idle' | 'generating' | 'speaking'

let activeUtterance: SpeechSynthesisUtterance | null = null
let activeAudio: HTMLAudioElement | null = null
let activeAudioUrl: string | null = null
let readAttempt = 0

function browserSpeechSynthesis() {
  return import.meta.client ? window.speechSynthesis : null
}

function cleanSpeechText(text: string) {
  return text
    .replace(/```[\s\S]*?```/g, ' code block ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/^\s{0,3}>\s?/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/[*_~#]/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function speechTextForMessage(message: WebChatMessage) {
  return cleanSpeechText(messageSpeechText(message))
}

const languagePatterns: Array<{ lang: string, pattern: RegExp }> = [
  { lang: 'sk-SK', pattern: /[áäčďéíľĺňóôŕšťúýž]|\b(ako|alebo|preto|ktor[ýáé]|môže|môžem|odpoveď|správ[aei]|tento|táto|bolo|bude|nie je|áno)\b/i },
  { lang: 'cs-CZ', pattern: /[ěůř]|\b(jako|nebo|proto|kter[ýáé]|může|odpověď|správn[ěá]|tento|bylo|bude|není|ano)\b/i },
  { lang: 'pl-PL', pattern: /[ąćęłńóśźż]|\b(jak|albo|ponieważ|który|może|odpowiedź|będzie|nie jest|tak)\b/i },
  { lang: 'de-DE', pattern: /[äöüß]|\b(und|oder|nicht|dass|kann|antwort|werden|ist|eine|der|die|das)\b/i },
  { lang: 'fr-FR', pattern: /[àâçéèêëîïôùûüÿœ]|\b(et|ou|pas|que|peut|réponse|sera|est|une|les|des)\b/i },
  { lang: 'es-ES', pattern: /[¿¡áéíóúñü]|\b(y|o|no|que|puede|respuesta|será|está|una|los|las)\b/i },
  { lang: 'pt-PT', pattern: /[ãõáâçéêíóôú]|\b(e|ou|não|que|pode|resposta|será|está|uma|os|as)\b/i },
  { lang: 'it-IT', pattern: /\b(e|o|non|che|può|risposta|sarà|è|una|gli|dei)\b/i },
  { lang: 'uk-UA', pattern: /[іїєґ]/i },
  { lang: 'ru-RU', pattern: /[а-яё]/i },
  { lang: 'ja-JP', pattern: /[ぁ-んァ-ン]/ },
  { lang: 'ko-KR', pattern: /[가-힣]/ },
  { lang: 'zh-CN', pattern: /[\u4e00-\u9fff]/ }
]

function detectSpeechLanguage(text: string) {
  const sample = text.slice(0, 2000)
  return languagePatterns.find(({ pattern }) => pattern.test(sample))?.lang ?? 'en-US'
}

function selectSpeechVoice(synthesis: SpeechSynthesis, lang: string) {
  const voices = synthesis.getVoices()
  const preferredVoiceURI = readAloudWebSpeechVoiceURI()
  const languageCode = lang.split('-')[0]

  if (preferredVoiceURI) {
    const preferred = voices.find(voice => voice.voiceURI === preferredVoiceURI)
    if (preferred) return preferred
  }

  return voices.find(voice => voice.lang.toLowerCase() === lang.toLowerCase())
    ?? voices.find(voice => voice.lang.toLowerCase().startsWith(`${languageCode}-`))
    ?? null
}

export function useMessageReadAloud() {
  const api = useHermesApi()
  const toast = useToast()
  const speakingMessageId = useState<string | null>('chat-speaking-message-id', () => null)
  const generatingMessageId = useState<string | null>('chat-generating-speech-message-id', () => null)
  const status = computed<ReadAloudStatus>(() => {
    if (generatingMessageId.value) return 'generating'
    return speakingMessageId.value ? 'speaking' : 'idle'
  })
  const isSupported = computed(() => Boolean(browserSpeechSynthesis() && typeof SpeechSynthesisUtterance !== 'undefined'))

  function clearActiveAudio() {
    activeAudio?.pause()
    activeAudio = null
    if (activeAudioUrl) URL.revokeObjectURL(activeAudioUrl)
    activeAudioUrl = null
  }

  function stop() {
    readAttempt += 1
    const synthesis = browserSpeechSynthesis()
    if (synthesis) synthesis.cancel()
    activeUtterance = null
    clearActiveAudio()
    speakingMessageId.value = null
    generatingMessageId.value = null
  }

  async function resolveReadAloudText(message: WebChatMessage, attempt: number) {
    const text = speechTextForMessage(message)
    if (!text || readAloudContentMode() !== 'summary') return text

    generatingMessageId.value = message.id
    try {
      const summary = await api.generateReadAloudSummary({ text })
      if (readAttempt !== attempt) return ''
      return cleanSpeechText(summary.text)
    } catch {
      if (readAttempt === attempt) {
        toast.add({ color: 'error', title: 'Could not generate readable read-aloud summary.' })
      }
      return ''
    } finally {
      if (readAttempt === attempt) generatingMessageId.value = null
    }
  }

  function readWithWebSpeech(message: WebChatMessage, text: string) {
    const synthesis = browserSpeechSynthesis()
    if (!synthesis || typeof SpeechSynthesisUtterance === 'undefined') {
      toast.add({ color: 'error', title: 'Read aloud is not supported in this browser.' })
      return
    }

    const attempt = readAttempt
    const utterance = new SpeechSynthesisUtterance(text)
    const speechLanguage = detectSpeechLanguage(text)
    const voice = selectSpeechVoice(synthesis, speechLanguage)

    utterance.lang = voice?.lang ?? speechLanguage
    utterance.rate = readAloudSpeed()
    if (voice) utterance.voice = voice

    activeUtterance = utterance
    speakingMessageId.value = message.id

    utterance.onend = () => {
      if (activeUtterance !== utterance || readAttempt !== attempt) return
      activeUtterance = null
      speakingMessageId.value = null
    }

    utterance.onerror = (event) => {
      if (activeUtterance !== utterance || readAttempt !== attempt) return
      activeUtterance = null
      speakingMessageId.value = null
      if (event.error !== 'canceled' && event.error !== 'interrupted') {
        toast.add({ color: 'error', title: 'Could not read message aloud.' })
      }
    }

    synthesis.speak(utterance)
  }

  async function readWithBackendTts(message: WebChatMessage, text: string) {
    const attempt = readAttempt
    generatingMessageId.value = message.id

    try {
      const blob = await api.synthesizeSpeech({ text, speed: readAloudSpeed() })
      if (readAttempt !== attempt) return

      const audioUrl = URL.createObjectURL(blob)
      const audio = new Audio(audioUrl)
      activeAudio = audio
      activeAudioUrl = audioUrl
      generatingMessageId.value = null
      speakingMessageId.value = message.id

      audio.onended = () => {
        if (activeAudio !== audio || readAttempt !== attempt) return
        clearActiveAudio()
        speakingMessageId.value = null
      }
      audio.onerror = () => {
        if (activeAudio !== audio || readAttempt !== attempt) return
        clearActiveAudio()
        speakingMessageId.value = null
        toast.add({ color: 'error', title: 'Could not play generated speech audio.' })
      }

      await audio.play()
    } catch {
      if (readAttempt !== attempt) return
      toast.add({ color: 'error', title: 'Could not generate speech audio.' })
      generatingMessageId.value = null
      speakingMessageId.value = null
      clearActiveAudio()
    }
  }

  async function read(message: WebChatMessage) {
    if (speakingMessageId.value === message.id || generatingMessageId.value === message.id) {
      stop()
      return
    }

    stop()
    const attempt = readAttempt
    const text = await resolveReadAloudText(message, attempt)
    if (!text || readAttempt !== attempt) return

    const engine = readAloudEngine()
    if (engine === 'backend-tts') {
      await readWithBackendTts(message, text)
      return
    }

    readWithWebSpeech(message, text)
  }

  return {
    generatingMessageId,
    isSupported,
    speakingMessageId,
    status,
    read,
    stop
  }
}
