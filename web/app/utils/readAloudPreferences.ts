export type ReadAloudContentMode = 'full' | 'summary'
export type ReadAloudEngine = 'web-speech' | 'backend-tts'

const autoReadPreferenceKey = 'hermes.readAloud.autoReadResponses'
const contentModePreferenceKey = 'hermes.readAloud.contentMode'
const enginePreferenceKey = 'hermes.readAloud.engine'
const speedPreferenceKey = 'hermes.readAloud.speed'
const webSpeechVoicePreferenceKey = 'hermes.readAloud.webSpeechVoiceURI'
const defaultContentMode: ReadAloudContentMode = 'full'
const defaultEngine: ReadAloudEngine = 'web-speech'
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
  return value === 'web-speech' || value === 'backend-tts'
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
  return isReadAloudEngine(stored) ? stored : defaultEngine
}

export function setReadAloudEngine(engine: ReadAloudEngine) {
  setStoredPreference(enginePreferenceKey, engine)
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
