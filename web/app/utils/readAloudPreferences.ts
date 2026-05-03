export type ReadAloudContentMode = 'full' | 'summary'
export type ReadAloudEngine = 'web-speech' | 'edge-tts' | 'elevenlabs'
export type VoiceInputProvider = 'browser' | 'elevenlabs' | 'openai'

const legacyBackendEngine = 'backend-tts'
const autoReadPreferenceKey = 'hermes.readAloud.autoReadResponses'
const contentModePreferenceKey = 'hermes.readAloud.contentMode'
const enginePreferenceKey = 'hermes.readAloud.engine'
const elevenLabsApiKeyPreferenceKey = 'hermes.readAloud.elevenLabsApiKey'
const openAIApiKeyPreferenceKey = 'hermes.voiceInput.openAIApiKey'
const voiceInputProviderPreferenceKey = 'hermes.voiceInput.provider'
const speedPreferenceKey = 'hermes.readAloud.speed'
const webSpeechVoicePreferenceKey = 'hermes.readAloud.webSpeechVoiceURI'
const defaultContentMode: ReadAloudContentMode = 'full'
const defaultEngine: ReadAloudEngine = 'web-speech'
const defaultVoiceInputProvider: VoiceInputProvider = 'browser'
const defaultSpeed = 1
const minSpeed = 0.5
const maxSpeed = 2

function isClient() {
  return typeof window !== 'undefined'
}

function isReadAloudContentMode(value: string | null): value is ReadAloudContentMode {
  return value === 'full' || value === 'summary'
}

function isReadAloudEngine(value: string | null): value is ReadAloudEngine {
  return value === 'web-speech' || value === 'edge-tts' || value === 'elevenlabs'
}

function isVoiceInputProvider(value: string | null): value is VoiceInputProvider {
  return value === 'browser' || value === 'elevenlabs' || value === 'openai'
}

function storedPreference(key: string) {
  if (!isClient()) return null
  const value = window.localStorage.getItem(key)?.trim()
  return value || null
}

function setStoredPreference(key: string, value: string | null) {
  if (!isClient()) return
  const normalized = value?.trim()
  if (normalized) {
    window.localStorage.setItem(key, normalized)
    return
  }
  window.localStorage.removeItem(key)
}

export function readAloudAutoReadResponsesEnabled() {
  return storedPreference(autoReadPreferenceKey) === 'true'
}

export function setReadAloudAutoReadResponsesEnabled(enabled: boolean) {
  setStoredPreference(autoReadPreferenceKey, enabled ? 'true' : null)
}

export function readAloudContentMode(): ReadAloudContentMode {
  const stored = storedPreference(contentModePreferenceKey)
  return isReadAloudContentMode(stored) ? stored : defaultContentMode
}

export function setReadAloudContentMode(mode: ReadAloudContentMode) {
  setStoredPreference(contentModePreferenceKey, mode === defaultContentMode ? null : mode)
}

export function readAloudEngine(): ReadAloudEngine {
  const stored = storedPreference(enginePreferenceKey)
  if (stored === legacyBackendEngine) return 'edge-tts'
  return isReadAloudEngine(stored) ? stored : defaultEngine
}

export function setReadAloudEngine(engine: ReadAloudEngine) {
  setStoredPreference(enginePreferenceKey, engine === defaultEngine ? null : engine)
}

export function readAloudElevenLabsApiKey() {
  return storedPreference(elevenLabsApiKeyPreferenceKey)
}

export function setReadAloudElevenLabsApiKey(apiKey: string | null) {
  setStoredPreference(elevenLabsApiKeyPreferenceKey, apiKey)
}

export function voiceInputOpenAIApiKey() {
  return storedPreference(openAIApiKeyPreferenceKey)
}

export function setVoiceInputOpenAIApiKey(apiKey: string | null) {
  setStoredPreference(openAIApiKeyPreferenceKey, apiKey)
}

export function voiceInputProvider(): VoiceInputProvider {
  const stored = storedPreference(voiceInputProviderPreferenceKey)
  return isVoiceInputProvider(stored) ? stored : defaultVoiceInputProvider
}

export function setVoiceInputProvider(provider: VoiceInputProvider) {
  setStoredPreference(voiceInputProviderPreferenceKey, provider === defaultVoiceInputProvider ? null : provider)
}

export function readAloudSpeed() {
  const stored = Number(storedPreference(speedPreferenceKey))
  if (!Number.isFinite(stored)) return defaultSpeed
  return Math.min(maxSpeed, Math.max(minSpeed, stored))
}

export function setReadAloudSpeed(speed: number) {
  const normalized = Math.min(maxSpeed, Math.max(minSpeed, speed))
  setStoredPreference(speedPreferenceKey, normalized === defaultSpeed ? null : String(normalized))
}

export function readAloudWebSpeechVoiceURI() {
  return storedPreference(webSpeechVoicePreferenceKey)
}

export function setReadAloudWebSpeechVoiceURI(voiceURI: string | null) {
  setStoredPreference(webSpeechVoicePreferenceKey, voiceURI)
}
