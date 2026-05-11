import type { AcpChatMessage } from '~/types/acp-chat'
import type { ReadAloudEngine } from '~/utils/readAloudPreferences'
import { detectReadAloudLanguage, readAloudLanguageLocale } from '../../shared/readAloud/language'
import { acpMessageSpeechText } from '~/utils/acpMessageMetadata'
import {
  readAloudElevenLabsApiKey,
  readAloudEngine,
  readAloudSpeed,
  readAloudWebSpeechVoiceURI
} from '~/utils/readAloudPreferences'

type ReadAloudStatus = 'idle' | 'generating' | 'speaking'

let activeUtterance: SpeechSynthesisUtterance | null = null
let activeAudio: HTMLAudioElement | null = null
let activeAudioUrl: string | null = null
let activeController: AbortController | null = null
let readAttempt = 0

function browserSpeechSynthesis() {
  return import.meta.client ? window.speechSynthesis : null
}

function revokeActiveAudioUrl() {
  if (!activeAudioUrl) return
  URL.revokeObjectURL(activeAudioUrl)
  activeAudioUrl = null
}

function voiceLanguageMatches(voice: SpeechSynthesisVoice, locale: string) {
  const language = locale.split('-')[0]
  const voiceLanguage = voice.lang.toLowerCase()
  return voiceLanguage === locale.toLowerCase() || voiceLanguage.startsWith(`${language}-`)
}

function selectSpeechVoice(synthesis: SpeechSynthesis, text: string) {
  const voices = synthesis.getVoices()
  const preferredVoiceURI = readAloudWebSpeechVoiceURI()
  if (preferredVoiceURI) {
    return voices.find(voice => voice.voiceURI === preferredVoiceURI) ?? null
  }

  const locale = readAloudLanguageLocale(detectReadAloudLanguage(text))
  return voices.find(voice => voice.lang.toLowerCase() === locale.toLowerCase())
    ?? voices.find(voice => voiceLanguageMatches(voice, locale))
    ?? null
}

function engineLabel(engine: ReadAloudEngine) {
  return engine === 'elevenlabs' ? 'ElevenLabs' : 'Edge TTS'
}

export function useAcpMessageReadAloud() {
  const toast = useToast()
  const speakingMessageId = useState<string | null>('acp-speaking-message-id', () => null)
  const generatingMessageId = useState<string | null>('acp-generating-speech-message-id', () => null)
  const speakingSessionId = useState<string | null>('acp-speaking-session-id', () => null)
  const generatingSessionId = useState<string | null>('acp-generating-speech-session-id', () => null)
  const status = computed<ReadAloudStatus>(() => {
    if (generatingMessageId.value || generatingSessionId.value) return 'generating'
    return speakingMessageId.value || speakingSessionId.value ? 'speaking' : 'idle'
  })
  const isSupported = computed(() => {
    if (!import.meta.client) return false
    return Boolean(browserSpeechSynthesis() && typeof SpeechSynthesisUtterance !== 'undefined') || typeof Audio !== 'undefined'
  })

  function clearSpeakingState(messageId?: string) {
    if (messageId && speakingMessageId.value !== messageId) return
    speakingMessageId.value = null
    speakingSessionId.value = null
  }

  function clearGeneratingState(messageId?: string) {
    if (messageId && generatingMessageId.value !== messageId) return
    generatingMessageId.value = null
    generatingSessionId.value = null
  }

  function stop() {
    readAttempt += 1
    const synthesis = browserSpeechSynthesis()
    if (synthesis) synthesis.cancel()
    activeUtterance = null

    if (activeAudio) {
      activeAudio.pause()
      activeAudio.src = ''
      activeAudio = null
    }
    revokeActiveAudioUrl()

    activeController?.abort()
    activeController = null
    clearGeneratingState()
    clearSpeakingState()
  }

  function readWithWebSpeech(message: AcpChatMessage, text: string, attempt: number) {
    const synthesis = browserSpeechSynthesis()
    if (!synthesis || typeof SpeechSynthesisUtterance === 'undefined') {
      toast.add({ color: 'error', title: 'Browser Web Speech is not supported in this browser.' })
      return
    }

    const utterance = new SpeechSynthesisUtterance(text)
    const voice = selectSpeechVoice(synthesis, text)

    if (voice) {
      utterance.lang = voice.lang
      utterance.voice = voice
    } else {
      utterance.lang = readAloudLanguageLocale(detectReadAloudLanguage(text))
    }
    utterance.rate = readAloudSpeed()

    activeUtterance = utterance
    speakingMessageId.value = message.id
    speakingSessionId.value = message.sessionId

    utterance.onend = () => {
      if (activeUtterance !== utterance || readAttempt !== attempt) return
      activeUtterance = null
      clearSpeakingState(message.id)
    }

    utterance.onerror = (event) => {
      if (activeUtterance !== utterance || readAttempt !== attempt) return
      activeUtterance = null
      clearSpeakingState(message.id)
      if (event.error !== 'canceled' && event.error !== 'interrupted') {
        toast.add({ color: 'error', title: 'Could not read message aloud.' })
      }
    }

    synthesis.speak(utterance)
  }

  async function readWithBackendSpeech(message: AcpChatMessage, text: string, engine: Exclude<ReadAloudEngine, 'web-speech'>, attempt: number) {
    if (typeof Audio === 'undefined') {
      toast.add({ color: 'error', title: 'Audio playback is not supported in this browser.' })
      return
    }

    const controller = new AbortController()
    activeController = controller
    generatingMessageId.value = message.id
    generatingSessionId.value = message.sessionId

    try {
      const response = await fetch('/api/app/read-aloud/speech', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          text,
          engine,
          speed: readAloudSpeed(),
          apiKey: engine === 'elevenlabs' ? readAloudElevenLabsApiKey() : null
        })
      })

      if (!response.ok) throw new Error(await response.text())
      const wasTruncated = response.headers.get('X-Hermesum-Read-Aloud-Truncated') === 'true'
      const maxLength = response.headers.get('X-Hermesum-Read-Aloud-Max-Length')
      const blob = await response.blob()
      if (readAttempt !== attempt) return
      if (wasTruncated) {
        toast.add({
          color: 'warning',
          title: `${engineLabel(engine)} text was shortened for read aloud.`,
          description: maxLength ? `Reading the first ${maxLength} characters, which is the configured limit for this engine.` : undefined
        })
      }

      const audioUrl = URL.createObjectURL(blob)
      const audio = new Audio(audioUrl)
      activeAudioUrl = audioUrl
      activeAudio = audio

      audio.onended = () => {
        if (activeAudio !== audio || readAttempt !== attempt) return
        activeAudio = null
        revokeActiveAudioUrl()
        clearSpeakingState(message.id)
      }
      audio.onerror = () => {
        if (activeAudio !== audio || readAttempt !== attempt) return
        activeAudio = null
        revokeActiveAudioUrl()
        clearSpeakingState(message.id)
        toast.add({ color: 'error', title: `Could not play ${engineLabel(engine)} audio.` })
      }

      await audio.play()
      if (activeAudio !== audio || readAttempt !== attempt) return
      speakingMessageId.value = message.id
      speakingSessionId.value = message.sessionId
    } catch (error) {
      if (controller.signal.aborted || readAttempt !== attempt) return
      toast.add({ color: 'error', title: `${engineLabel(engine)} read aloud failed.`, description: error instanceof Error ? error.message : undefined })
    } finally {
      if (activeController === controller) activeController = null
      clearGeneratingState(message.id)
    }
  }

  function stopSession(sessionId: string) {
    if (generatingSessionId.value !== sessionId && speakingSessionId.value !== sessionId) return
    stop()
  }

  function read(message: AcpChatMessage) {
    if (speakingMessageId.value === message.id || generatingMessageId.value === message.id) {
      stop()
      return
    }

    if (!isSupported.value) {
      toast.add({ color: 'error', title: 'Read aloud is not supported in this browser.' })
      return
    }

    const text = acpMessageSpeechText(message)
    if (!text) return

    stop()
    const attempt = readAttempt
    const engine = readAloudEngine()
    if (engine === 'web-speech') {
      readWithWebSpeech(message, text, attempt)
      return
    }
    void readWithBackendSpeech(message, text, engine, attempt)
  }

  return {
    isSupported,
    speakingMessageId,
    generatingMessageId,
    speakingSessionId,
    generatingSessionId,
    status,
    read,
    stop,
    stopSession
  }
}
