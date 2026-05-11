export type BackendReadAloudEngine = 'edge-tts' | 'elevenlabs'

const maxTextLengthByEngine = {
  'edge-tts': 12_000,
  elevenlabs: 5_000
} satisfies Record<BackendReadAloudEngine, number>

export function readAloudMaxTextLength(engine: BackendReadAloudEngine) {
  return maxTextLengthByEngine[engine]
}

export function fitReadAloudTextToEngine(text: string, engine: BackendReadAloudEngine) {
  const normalized = text.trim()
  const maxLength = readAloudMaxTextLength(engine)

  if (normalized.length <= maxLength) {
    return { text: normalized, truncated: false, maxLength }
  }

  return {
    text: normalized.slice(0, maxLength).trimEnd(),
    truncated: true,
    maxLength
  }
}
