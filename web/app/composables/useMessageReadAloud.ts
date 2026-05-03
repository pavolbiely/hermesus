import type { WebChatMessage } from '~/types/web-chat'
import { messageSpeechText } from '~/utils/chatMessages'
import { playNotificationSound } from '~/utils/notificationSound'
import {
  readAloudContentMode,
  readAloudEngine,
  readAloudSpeed,
  readAloudWebSpeechVoiceURI
} from '~/utils/readAloudPreferences'

type ReadAloudStatus = 'idle' | 'generating' | 'speaking'
type ReadAloudPlaybackSource =
  | 'readable-summary'
  | 'web-speech'
  | 'edge-tts-stream'
  | 'edge-tts-fallback-generating'
  | 'edge-tts-fallback-blob'
type ReadAloudCacheStatus = 'cached' | 'generated'
type CachedSpeechBlob = {
  blob: Blob
  cacheStatus: ReadAloudCacheStatus
}
type ReadAloudOptions = {
  queue?: boolean
}
type PreparedReadAloud =
  | { engine: 'web-speech', text: string }
  | { engine: 'backend-tts', text: string, speed: number }
type QueuedReadAloudMessage = {
  message: WebChatMessage
  attempt: number
  prepared: Promise<PreparedReadAloud | null>
}

const READ_ALOUD_CACHE_LIMIT = 30

let activeUtterance: SpeechSynthesisUtterance | null = null
let activeAudio: HTMLAudioElement | null = null
let activeAudioUrl: string | null = null
let activeAbortController: AbortController | null = null
let activeCompletion: (() => void) | null = null
let readAttempt = 0
let readQueue: QueuedReadAloudMessage[] = []
let queueProcessing = false
const summaryCache = new Map<string, Promise<string>>()
const speechBlobCache = new Map<string, Promise<CachedSpeechBlob>>()

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

function rememberCachedValue<TKey, TValue>(cache: Map<TKey, Promise<TValue>>, key: TKey, value: Promise<TValue>) {
  if (cache.has(key)) cache.delete(key)
  cache.set(key, value)
  while (cache.size > READ_ALOUD_CACHE_LIMIT) {
    const oldestKey = cache.keys().next().value
    if (oldestKey === undefined) break
    cache.delete(oldestKey)
  }
}

function cachedReadAloudSummary(text: string, generate: () => Promise<string>) {
  const cached = summaryCache.get(text)
  if (cached) {
    rememberCachedValue(summaryCache, text, cached)
    return cached
  }

  const summary = generate()
    .then(cleanSpeechText)
    .catch((error: unknown) => {
      summaryCache.delete(text)
      throw error
    })
  rememberCachedValue(summaryCache, text, summary)
  return summary
}

function readResponseCacheStatus(value: string | null): ReadAloudCacheStatus {
  return value === 'hit' ? 'cached' : 'generated'
}

function cachedSpeechBlob(text: string, speed: number, synthesize: () => Promise<CachedSpeechBlob>) {
  const key = `${speed}:${text}`
  const cached = speechBlobCache.get(key)
  if (cached) {
    const markedCached = cached.then(result => ({ ...result, cacheStatus: 'cached' as const }))
    rememberCachedValue(speechBlobCache, key, markedCached)
    return markedCached
  }

  const blob = synthesize().catch((error: unknown) => {
    speechBlobCache.delete(key)
    throw error
  })
  rememberCachedValue(speechBlobCache, key, blob)
  return blob
}

export function useMessageReadAloud() {
  const api = useHermesApi()
  const toast = useToast()
  const speakingMessageId = useState<string | null>('chat-speaking-message-id', () => null)
  const generatingMessageId = useState<string | null>('chat-generating-speech-message-id', () => null)
  const playbackSources = useState<Record<string, ReadAloudPlaybackSource>>('chat-read-aloud-playback-sources', () => ({}))
  const playbackCacheStatuses = useState<Record<string, ReadAloudCacheStatus>>('chat-read-aloud-cache-statuses', () => ({}))
  const status = computed<ReadAloudStatus>(() => {
    if (generatingMessageId.value) return 'generating'
    return speakingMessageId.value ? 'speaking' : 'idle'
  })
  const isSupported = computed(() => Boolean(browserSpeechSynthesis() && typeof SpeechSynthesisUtterance !== 'undefined'))

  function setPlaybackSource(messageId: string, source: ReadAloudPlaybackSource) {
    playbackSources.value = { ...playbackSources.value, [messageId]: source }
  }

  function clearPlaybackSource(messageId: string) {
    const { [messageId]: _removedSource, ...remainingSources } = playbackSources.value
    const { [messageId]: _removedCacheStatus, ...remainingCacheStatuses } = playbackCacheStatuses.value
    playbackSources.value = remainingSources
    playbackCacheStatuses.value = remainingCacheStatuses
  }

  function clearAllPlaybackSources() {
    playbackSources.value = {}
  }

  function setPlaybackCacheStatus(messageId: string, cacheStatus: ReadAloudCacheStatus) {
    playbackCacheStatuses.value = { ...playbackCacheStatuses.value, [messageId]: cacheStatus }
  }

  function clearAllPlaybackCacheStatuses() {
    playbackCacheStatuses.value = {}
  }

  function finishActiveSpeech() {
    const completion = activeCompletion
    activeCompletion = null
    completion?.()
  }

  function clearActiveAudio() {
    activeAbortController?.abort()
    activeAbortController = null
    activeAudio?.pause()
    activeAudio = null
    if (activeAudioUrl) URL.revokeObjectURL(activeAudioUrl)
    activeAudioUrl = null
  }

  function stop() {
    readAttempt += 1
    readQueue = []
    const synthesis = browserSpeechSynthesis()
    if (synthesis) synthesis.cancel()
    activeUtterance = null
    clearActiveAudio()
    finishActiveSpeech()
    speakingMessageId.value = null
    generatingMessageId.value = null
    clearAllPlaybackSources()
    clearAllPlaybackCacheStatuses()
  }

  async function resolveReadAloudText(message: WebChatMessage, attempt: number) {
    const text = speechTextForMessage(message)
    if (!text || readAloudContentMode() !== 'summary') return text

    generatingMessageId.value = message.id
    setPlaybackSource(message.id, 'readable-summary')
    try {
      const summary = await cachedReadAloudSummary(text, async () => {
        const response = await api.generateReadAloudSummary({ text })
        return response.text
      })
      if (readAttempt !== attempt) return ''
      return summary
    } catch {
      if (readAttempt === attempt) {
        toast.add({ color: 'error', title: 'Could not generate readable read-aloud summary.' })
      }
      return ''
    } finally {
      if (readAttempt === attempt) {
        generatingMessageId.value = null
        clearPlaybackSource(message.id)
      }
    }
  }

  function readWithWebSpeech(message: WebChatMessage, text: string, attempt: number) {
    return new Promise<void>((resolve) => {
      const synthesis = browserSpeechSynthesis()
      if (!synthesis || typeof SpeechSynthesisUtterance === 'undefined') {
        toast.add({ color: 'error', title: 'Read aloud is not supported in this browser.' })
        resolve()
        return
      }

      const utterance = new SpeechSynthesisUtterance(text)
      const speechLanguage = detectSpeechLanguage(text)
      const voice = selectSpeechVoice(synthesis, speechLanguage)

      utterance.lang = voice?.lang ?? speechLanguage
      utterance.rate = readAloudSpeed()
      if (voice) utterance.voice = voice

      activeUtterance = utterance
      activeCompletion = resolve
      speakingMessageId.value = message.id
      setPlaybackSource(message.id, 'web-speech')

      utterance.onend = () => {
        if (activeUtterance !== utterance || readAttempt !== attempt) return
        activeUtterance = null
        speakingMessageId.value = null
        clearPlaybackSource(message.id)
        finishActiveSpeech()
      }

      utterance.onerror = (event) => {
        if (activeUtterance !== utterance || readAttempt !== attempt) return
        activeUtterance = null
        speakingMessageId.value = null
        clearPlaybackSource(message.id)
        if (event.error !== 'canceled' && event.error !== 'interrupted') {
          toast.add({ color: 'error', title: 'Could not read message aloud.' })
        }
        finishActiveSpeech()
      }

      synthesis.speak(utterance)
    })
  }

  async function synthesizeSpeechBlob(message: WebChatMessage, text: string, attempt: number) {
    generatingMessageId.value = message.id
    setPlaybackSource(message.id, 'edge-tts-fallback-generating')

    try {
      const speed = readAloudSpeed()
      const result = await cachedSpeechBlob(text, speed, async () => {
        const response = await api.synthesizeSpeechWithMetadata({ text, speed })
        return {
          blob: response.blob,
          cacheStatus: readResponseCacheStatus(response.cacheStatus)
        }
      })
      if (readAttempt !== attempt) return null
      setPlaybackCacheStatus(message.id, result.cacheStatus)
      return result.blob
    } catch {
      if (readAttempt === attempt) {
        toast.add({ color: 'error', title: 'Could not generate speech audio.' })
      }
      return null
    } finally {
      if (readAttempt === attempt) {
        generatingMessageId.value = null
        clearPlaybackSource(message.id)
      }
    }
  }

  async function playBackendTtsBlob(message: WebChatMessage, blob: Blob, attempt: number) {
    const audioUrl = URL.createObjectURL(blob)
    const audio = new Audio(audioUrl)
    activeAudio = audio
    activeAudioUrl = audioUrl
    speakingMessageId.value = message.id
    setPlaybackSource(message.id, 'edge-tts-fallback-blob')

    await new Promise<void>((resolve) => {
      activeCompletion = resolve

      audio.onended = () => {
        if (activeAudio !== audio || readAttempt !== attempt) return
        clearActiveAudio()
        speakingMessageId.value = null
        clearPlaybackSource(message.id)
        finishActiveSpeech()
      }
      audio.onerror = () => {
        if (activeAudio !== audio || readAttempt !== attempt) return
        clearActiveAudio()
        speakingMessageId.value = null
        clearPlaybackSource(message.id)
        toast.add({ color: 'error', title: 'Could not play generated speech audio.' })
        finishActiveSpeech()
      }

      void audio.play().catch(() => {
        if (readAttempt !== attempt) return
        clearActiveAudio()
        speakingMessageId.value = null
        clearPlaybackSource(message.id)
        toast.add({ color: 'error', title: 'Could not play generated speech audio.' })
        finishActiveSpeech()
      })
    })
  }

  function appendSourceBuffer(sourceBuffer: SourceBuffer, chunk: Uint8Array) {
    return new Promise<void>((resolve, reject) => {
      sourceBuffer.addEventListener('updateend', () => resolve(), { once: true })
      sourceBuffer.addEventListener('error', () => reject(new Error('Could not append streamed speech audio.')), { once: true })
      const buffer = new ArrayBuffer(chunk.byteLength)
      new Uint8Array(buffer).set(chunk)
      sourceBuffer.appendBuffer(buffer)
    })
  }

  async function pipeSpeechStreamToMediaSource(
    text: string,
    speed: number,
    mediaSource: MediaSource,
    signal: AbortSignal,
    onCacheStatus: (cacheStatus: ReadAloudCacheStatus) => void
  ) {
    const sourceBuffer = mediaSource.addSourceBuffer('audio/mpeg')
    const response = await api.streamSpeech({ text, speed }, signal)
    onCacheStatus(readResponseCacheStatus(response.headers.get('X-Hermes-TTS-Cache')))
    const reader = response.body?.getReader()
    if (!reader) throw new Error('Speech stream returned no body.')

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      if (value?.byteLength) await appendSourceBuffer(sourceBuffer, value)
    }

    if (mediaSource.readyState === 'open' && !sourceBuffer.updating) mediaSource.endOfStream()
  }

  async function playBackendTtsStream(message: WebChatMessage, text: string, speed: number, attempt: number) {
    if (typeof MediaSource === 'undefined' || !MediaSource.isTypeSupported('audio/mpeg')) {
      throw new Error('Streaming audio playback is not supported in this browser.')
    }

    const controller = new AbortController()
    const mediaSource = new MediaSource()
    const audioUrl = URL.createObjectURL(mediaSource)
    const audio = new Audio(audioUrl)
    activeAbortController = controller
    activeAudio = audio
    activeAudioUrl = audioUrl
    speakingMessageId.value = message.id
    setPlaybackSource(message.id, 'edge-tts-stream')

    await new Promise<void>((resolve, reject) => {
      activeCompletion = resolve

      audio.onended = () => {
        if (activeAudio !== audio || readAttempt !== attempt) return
        clearActiveAudio()
        speakingMessageId.value = null
        clearPlaybackSource(message.id)
        finishActiveSpeech()
      }
      audio.onerror = () => {
        if (activeAudio !== audio || readAttempt !== attempt) return
        clearActiveAudio()
        speakingMessageId.value = null
        clearPlaybackSource(message.id)
        reject(new Error('Could not play streamed speech audio.'))
        finishActiveSpeech()
      }
      mediaSource.addEventListener('sourceopen', () => {
        pipeSpeechStreamToMediaSource(
          text,
          speed,
          mediaSource,
          controller.signal,
          cacheStatus => setPlaybackCacheStatus(message.id, cacheStatus)
        ).catch((error: unknown) => {
          if (controller.signal.aborted || readAttempt !== attempt) return
          reject(error)
        })
      }, { once: true })

      void audio.play().catch(reject)
    })
  }

  async function playBackendTts(message: WebChatMessage, text: string, speed: number, attempt: number) {
    try {
      await playBackendTtsStream(message, text, speed, attempt)
      return
    } catch {
      if (readAttempt !== attempt) return
      clearActiveAudio()
      speakingMessageId.value = null
      clearPlaybackSource(message.id)
    }

    const blob = await synthesizeSpeechBlob(message, text, attempt)
    if (!blob || readAttempt !== attempt) return
    await playBackendTtsBlob(message, blob, attempt)
  }

  async function prepareReadAloud(message: WebChatMessage, attempt: number): Promise<PreparedReadAloud | null> {
    const text = await resolveReadAloudText(message, attempt)
    if (!text || readAttempt !== attempt) return null

    const engine = readAloudEngine()
    if (engine === 'backend-tts') {
      return { engine, text, speed: readAloudSpeed() }
    }

    return { engine, text }
  }

  async function playPreparedReadAloud(message: WebChatMessage, prepared: PreparedReadAloud, attempt: number) {
    if (prepared.engine === 'backend-tts') {
      await playBackendTts(message, prepared.text, prepared.speed, attempt)
      return
    }

    await readWithWebSpeech(message, prepared.text, attempt)
  }

  async function readImmediately(message: WebChatMessage, attempt: number) {
    const prepared = await prepareReadAloud(message, attempt)
    if (!prepared || readAttempt !== attempt) return
    await playPreparedReadAloud(message, prepared, attempt)
  }

  async function processQueue() {
    if (queueProcessing) return
    queueProcessing = true

    try {
      let playedCount = 0
      while (readQueue.length) {
        const item = readQueue.shift()
        if (!item || readAttempt !== item.attempt) continue
        const prepared = await item.prepared
        if (!prepared || readAttempt !== item.attempt) continue
        if (playedCount > 0) void playNotificationSound('read-aloud-next')
        playedCount += 1
        await playPreparedReadAloud(item.message, prepared, item.attempt)
      }
    } finally {
      queueProcessing = false
    }
  }

  async function read(message: WebChatMessage, options: ReadAloudOptions = {}) {
    const activeMessageId = speakingMessageId.value || generatingMessageId.value
    if (activeMessageId === message.id) {
      if (!options.queue) stop()
      return
    }

    if (readQueue.some(item => item.message.id === message.id)) return

    if (!options.queue) stop()
    const attempt = readAttempt
    readQueue.push({
      message,
      attempt,
      prepared: prepareReadAloud(message, attempt)
    })
    await processQueue()
  }

  return {
    generatingMessageId,
    isSupported,
    playbackCacheStatuses,
    playbackSources,
    speakingMessageId,
    status,
    read,
    stop
  }
}
