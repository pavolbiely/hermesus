export type NotificationSoundVariant = 'default' | 'attention' | 'sent'

type NotificationSoundState = {
  activeVisibleChat: boolean
  latestContentVisible: boolean
}

type Tone = {
  offset: number
  frequency: number
  duration: number
}

type AudioContextConstructor = typeof AudioContext

type WindowWithAudioContext = Window & {
  AudioContext?: AudioContextConstructor
  webkitAudioContext?: AudioContextConstructor
}

export type NotificationSoundDebugState = {
  supported: boolean
  enabled: boolean
  contextState: AudioContextState | 'missing' | 'unknown'
  unlockInstalled: boolean
  lastAttempt?: string
  lastPlayedAt: number
}

let audioContext: AudioContext | undefined
let enabled = false
let unlockInstalled = false
let lastPlayedAt = 0
let lastAttempt: string | undefined

function isClient() {
  return typeof window !== 'undefined'
}

function audioContextConstructor() {
  if (!isClient()) return undefined
  const audioWindow = window as WindowWithAudioContext
  return audioWindow.AudioContext || audioWindow.webkitAudioContext
}

function getAudioContext() {
  const AudioContextClass = audioContextConstructor()
  if (!AudioContextClass) return undefined
  audioContext ||= new AudioContextClass()
  return audioContext
}

export function notificationSoundVariant(state: NotificationSoundState): NotificationSoundVariant {
  return state.activeVisibleChat && state.latestContentVisible ? 'default' : 'attention'
}

function tonesForVariant(variant: NotificationSoundVariant): Tone[] {
  if (variant === 'sent') {
    return [
      { offset: 0, frequency: 587, duration: 0.08 },
      { offset: 0.07, frequency: 880, duration: 0.11 }
    ]
  }

  if (variant === 'attention') {
    return [
      { offset: 0, frequency: 1568, duration: 0.34 },
      { offset: 0.018, frequency: 2093, duration: 0.28 },
      { offset: 0.046, frequency: 2637, duration: 0.22 },
      { offset: 0.082, frequency: 3136, duration: 0.16 }
    ]
  }

  return [
    { offset: 0, frequency: 880, duration: 0.1 },
    { offset: 0.08, frequency: 1175, duration: 0.1 }
  ]
}

export function notificationSoundDebugState(): NotificationSoundDebugState {
  const context = audioContext
  return {
    supported: Boolean(audioContextConstructor()),
    enabled,
    contextState: context?.state || (audioContextConstructor() ? 'unknown' : 'missing'),
    unlockInstalled,
    lastAttempt,
    lastPlayedAt
  }
}

export async function prepareNotificationSound() {
  if (!isClient()) return false

  enabled = true
  lastAttempt = 'prepare'

  const context = getAudioContext()
  if (!context) {
    lastAttempt = 'unsupported'
    return false
  }

  if (context.state === 'suspended') {
    await context.resume().catch(error => {
      lastAttempt = `resume-failed:${String(error?.name || error?.message || error)}`
    })
  }

  return context.state === 'running'
}

export function installNotificationSoundUnlock() {
  if (!isClient() || unlockInstalled) return
  unlockInstalled = true

  const unlock = () => {
    void prepareNotificationSound()
  }

  window.addEventListener('pointerdown', unlock, { passive: true })
  window.addEventListener('keydown', unlock)
  window.addEventListener('touchstart', unlock, { passive: true })
  window.addEventListener('wheel', unlock, { passive: true })
}

async function scheduleNotificationSound(variant: NotificationSoundVariant) {
  if (!isClient()) return false

  enabled = true
  lastAttempt = `play:${variant}`

  const context = getAudioContext()
  if (!context) {
    lastAttempt = 'unsupported'
    return false
  }

  if (context.state === 'suspended') {
    await context.resume().catch(error => {
      lastAttempt = `resume-failed:${String(error?.name || error?.message || error)}`
    })
  }
  if (context.state !== 'running') {
    lastAttempt = `not-running:${context.state}`
    return false
  }

  const now = Date.now()
  if (now - lastPlayedAt < 250) {
    lastAttempt = `throttled:${variant}`
    return false
  }
  lastPlayedAt = now

  const start = context.currentTime + 0.01
  const tones = tonesForVariant(variant)
  const volume = variant === 'attention' ? 0.16 : variant === 'sent' ? 0.08 : 0.09
  const end = Math.max(...tones.map(tone => tone.offset + tone.duration))
  const gain = context.createGain()

  gain.gain.setValueAtTime(0.0001, start)
  gain.gain.exponentialRampToValueAtTime(volume, start + 0.015)
  gain.gain.setValueAtTime(volume, start + Math.max(0.02, end - 0.08))
  gain.gain.exponentialRampToValueAtTime(0.0001, start + end)
  gain.connect(context.destination)

  for (const tone of tones) {
    const oscillator = context.createOscillator()
    oscillator.type = 'sine'
    oscillator.frequency.setValueAtTime(tone.frequency, start + tone.offset)
    oscillator.connect(gain)
    oscillator.start(start + tone.offset)
    oscillator.stop(start + tone.offset + tone.duration)
  }

  window.setTimeout(() => gain.disconnect(), (end + 0.1) * 1000)
  lastAttempt = `played:${variant}`
  return true
}

export function playNotificationSound(variant: NotificationSoundVariant = 'default') {
  return scheduleNotificationSound(variant)
}
