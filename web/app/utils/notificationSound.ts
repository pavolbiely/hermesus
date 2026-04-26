type NotificationSoundVariant = 'default' | 'attention'

type Tone = {
  offset: number
  frequency: number
  duration: number
}

let audioContext: AudioContext | undefined
let enabled = false
let lastPlayedAt = 0

function getAudioContext() {
  audioContext ||= new AudioContext()
  return audioContext
}

function tonesForVariant(variant: NotificationSoundVariant): Tone[] {
  if (variant === 'attention') {
    return [
      { offset: 0, frequency: 740, duration: 0.16 },
      { offset: 0.15, frequency: 988, duration: 0.18 },
      { offset: 0.33, frequency: 1319, duration: 0.22 }
    ]
  }

  return [
    { offset: 0, frequency: 880, duration: 0.1 },
    { offset: 0.08, frequency: 1175, duration: 0.1 }
  ]
}

export async function prepareNotificationSound() {
  if (import.meta.server) return

  enabled = true
  const context = getAudioContext()
  if (context.state === 'suspended') {
    await context.resume().catch(() => undefined)
  }
}

export function playNotificationSound(variant: NotificationSoundVariant = 'default') {
  if (import.meta.server || !enabled) return

  const now = Date.now()
  if (now - lastPlayedAt < 750) return
  lastPlayedAt = now

  const context = getAudioContext()
  void context.resume().catch(() => undefined)

  const start = context.currentTime
  const tones = tonesForVariant(variant)
  const volume = variant === 'attention' ? 0.11 : 0.06
  const end = Math.max(...tones.map(tone => tone.offset + tone.duration))
  const gain = context.createGain()

  gain.gain.setValueAtTime(0.0001, start)
  gain.gain.exponentialRampToValueAtTime(volume, start + 0.015)
  gain.gain.setValueAtTime(volume, start + Math.max(0.02, end - 0.08))
  gain.gain.exponentialRampToValueAtTime(0.0001, start + end)
  gain.connect(context.destination)

  for (const tone of tones) {
    const oscillator = context.createOscillator()
    oscillator.type = variant === 'attention' ? 'triangle' : 'sine'
    oscillator.frequency.setValueAtTime(tone.frequency, start + tone.offset)
    oscillator.connect(gain)
    oscillator.start(start + tone.offset)
    oscillator.stop(start + tone.offset + tone.duration)
  }

  window.setTimeout(() => gain.disconnect(), (end + 0.1) * 1000)
}
