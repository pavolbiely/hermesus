import { spawn } from 'node:child_process'
import { createError, defineEventHandler, readBody, setHeader } from 'h3'
import { detectReadAloudLanguage, edgeReadAloudVoice } from '../../../../shared/readAloud/language'

type SpeechRequest = {
  text?: string
  engine?: 'edge-tts' | 'elevenlabs'
  speed?: number
  apiKey?: string | null
}

const maxTextLength = 12_000
const elevenLabsDefaultVoiceId = 'pNInz6obpgDQGcFmaJgB'

function normalizeSpeed(value: unknown) {
  const speed = typeof value === 'number' && Number.isFinite(value) ? value : 1
  return Math.min(2, Math.max(0.5, speed))
}

function edgeRate(speed: number) {
  const percent = Math.round((speed - 1) * 100)
  return `${percent >= 0 ? '+' : ''}${percent}%`
}

function readPipe(stream: NodeJS.ReadableStream) {
  const chunks: Buffer[] = []
  return new Promise<Buffer>((resolve, reject) => {
    stream.on('data', chunk => chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)))
    stream.on('error', reject)
    stream.on('end', () => resolve(Buffer.concat(chunks)))
  })
}

function runEdgeTts(text: string, speed: number) {
  const language = detectReadAloudLanguage(text)
  const voice = edgeReadAloudVoice(language)
  const child = spawn('uv', [
    'run',
    '--no-project',
    '--with',
    'edge-tts',
    'python',
    '-c',
    `import asyncio, json, sys\nimport edge_tts\n\nasync def main():\n    request = json.load(sys.stdin)\n    communicate = edge_tts.Communicate(request["text"], request["voice"], rate=request["rate"])\n    async for chunk in communicate.stream():\n        if chunk.get("type") == "audio":\n            sys.stdout.buffer.write(chunk["data"])\n            sys.stdout.buffer.flush()\n\nasyncio.run(main())\n`
  ], { stdio: ['pipe', 'pipe', 'pipe'] })

  child.stdin.end(JSON.stringify({ text, voice, rate: edgeRate(speed) }))

  return Promise.all([readPipe(child.stdout), readPipe(child.stderr), new Promise<number | null>((resolve) => {
    child.on('close', resolve)
  })]).then(([audio, stderr, code]) => {
    if (code !== 0 || audio.length === 0) {
      throw createError({
        statusCode: 502,
        statusMessage: 'Edge TTS generation failed',
        message: stderr.toString('utf8').trim() || 'Edge TTS returned no audio.'
      })
    }
    return audio
  })
}

async function runElevenLabsTts(text: string, speed: number, apiKey?: string | null) {
  const key = apiKey?.trim() || process.env.ELEVENLABS_API_KEY
  if (!key) {
    throw createError({ statusCode: 400, statusMessage: 'ElevenLabs API key is required.' })
  }

  const response = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${elevenLabsDefaultVoiceId}?output_format=mp3_44100_128`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'xi-api-key': key
    },
    body: JSON.stringify({
      text,
      model_id: 'eleven_multilingual_v2',
      voice_settings: {
        stability: 0.5,
        similarity_boost: 0.75,
        speed: Math.min(1.2, Math.max(0.7, speed))
      }
    })
  })

  if (!response.ok) {
    throw createError({
      statusCode: response.status,
      statusMessage: 'ElevenLabs TTS generation failed',
      message: await response.text()
    })
  }

  return Buffer.from(await response.arrayBuffer())
}

export default defineEventHandler(async (event) => {
  const body = await readBody<SpeechRequest>(event)
  const text = body.text?.trim()
  if (!text) throw createError({ statusCode: 400, statusMessage: 'Text is required.' })
  if (text.length > maxTextLength) throw createError({ statusCode: 413, statusMessage: 'Text is too long for read aloud.' })

  const speed = normalizeSpeed(body.speed)
  const audio = body.engine === 'elevenlabs'
    ? await runElevenLabsTts(text, speed, body.apiKey)
    : await runEdgeTts(text, speed)

  setHeader(event, 'Content-Type', 'audio/mpeg')
  setHeader(event, 'Cache-Control', 'no-store')
  return audio
})
