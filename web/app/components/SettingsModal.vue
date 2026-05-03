<script setup lang="ts">
import type { DesktopNotificationPermission } from '~/utils/desktopNotifications'
import type { ReadAloudContentMode, ReadAloudEngine } from '~/utils/readAloudPreferences'
import {
  desktopNotificationPermission,
  desktopNotificationsEnabled,
  desktopNotificationsSupported,
  requestDesktopNotificationPermission,
  setDesktopNotificationsEnabled
} from '~/utils/desktopNotifications'
import {
  readAloudAutoReadResponsesEnabled,
  readAloudContentMode,
  readAloudEngine,
  readAloudSpeed,
  readAloudWebSpeechVoiceURI,
  setReadAloudAutoReadResponsesEnabled,
  setReadAloudContentMode,
  setReadAloudEngine,
  setReadAloudSpeed,
  setReadAloudWebSpeechVoiceURI
} from '~/utils/readAloudPreferences'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

type WebSpeechVoiceItem = {
  label: string
  value: string
  description: string
}

const permission = ref<DesktopNotificationPermission>('unsupported')
const enabled = ref(false)
const pending = ref(false)
const speechEngine = ref<ReadAloudEngine>('web-speech')
const speechContentMode = ref<ReadAloudContentMode>('full')
const speechSpeed = ref(1)
const autoReadResponses = ref(false)
const webSpeechVoiceURI = ref<string | null>(null)
const browserVoices = ref<SpeechSynthesisVoice[]>([])

const speechEngineItems = [
  {
    label: 'Browser Web Speech API',
    value: 'web-speech',
    description: 'Uses the browser and system voices. Fast, local, and no backend generation.'
  },
  {
    label: 'Edge TTS via Hermes',
    value: 'backend-tts',
    description: 'Generates audio through Hermes using Edge TTS with automatic language voice selection.'
  }
] satisfies Array<{ label: string, value: ReadAloudEngine, description: string }>

const speechContentModeItems = [
  {
    label: 'Full message',
    value: 'full',
    description: 'Read the assistant message as written, after basic Markdown cleanup.'
  },
  {
    label: 'Readable summary',
    value: 'summary',
    description: 'Ask Hermes to rewrite the response into natural spoken prose and avoid noisy code, file paths, CSS classes, and raw technical output.'
  }
] satisfies Array<{ label: string, value: ReadAloudContentMode, description: string }>

const speechSpeedItems = [
  { label: '0.5× — very slow', value: 0.5 },
  { label: '0.75× — slower', value: 0.75 },
  { label: '1× — normal', value: 1 },
  { label: '1.25× — faster', value: 1.25 },
  { label: '1.5× — fast', value: 1.5 },
  { label: '2× — very fast', value: 2 }
] satisfies Array<{ label: string, value: number }>

const webSpeechVoiceItems = computed<WebSpeechVoiceItem[]>(() => [
  {
    label: 'Auto-detect from message language',
    value: '__auto__',
    description: 'Pick the closest installed browser voice for each message.'
  },
  ...browserVoices.value.map(voice => ({
    label: `${voice.name} (${voice.lang})`,
    value: voice.voiceURI,
    description: voice.localService ? 'Local browser/system voice' : 'Remote browser voice'
  }))
])
const selectedWebSpeechVoice = computed(() => webSpeechVoiceURI.value ?? '__auto__')

const supported = computed(() => permission.value !== 'unsupported')
const blocked = computed(() => permission.value === 'denied')
const enabledAndGranted = computed(() => enabled.value && permission.value === 'granted')
const statusLabel = computed(() => {
  if (!supported.value) return 'Not supported in this browser'
  if (blocked.value) return 'Blocked in browser settings'
  if (enabledAndGranted.value) return 'Enabled'
  return 'Disabled'
})
const actionLabel = computed(() => {
  if (blocked.value) return 'Notifications blocked'
  if (!supported.value) return 'Notifications are not supported'
  if (enabledAndGranted.value) return 'Disable desktop notifications'
  return 'Enable desktop notifications'
})
const statusChipColor = computed(() => enabledAndGranted.value ? 'success' : 'error')

function browserSpeechSynthesis() {
  return import.meta.client ? window.speechSynthesis : null
}

function refreshBrowserVoices() {
  const synthesis = browserSpeechSynthesis()
  browserVoices.value = synthesis ? synthesis.getVoices() : []
}

function refreshState() {
  permission.value = desktopNotificationPermission()
  enabled.value = desktopNotificationsEnabled()
  speechEngine.value = readAloudEngine()
  speechContentMode.value = readAloudContentMode()
  speechSpeed.value = readAloudSpeed()
  autoReadResponses.value = readAloudAutoReadResponsesEnabled()
  webSpeechVoiceURI.value = readAloudWebSpeechVoiceURI()
  refreshBrowserVoices()
}

function updateSpeechEngine(value: ReadAloudEngine) {
  speechEngine.value = value
  setReadAloudEngine(value)
}

function updateSpeechContentMode(value: ReadAloudContentMode) {
  speechContentMode.value = value
  setReadAloudContentMode(value)
}

function updateSpeechSpeed(value: number) {
  speechSpeed.value = value
  setReadAloudSpeed(value)
}

function updateAutoReadResponses(value: boolean) {
  autoReadResponses.value = value
  setReadAloudAutoReadResponsesEnabled(value)
}

function updateWebSpeechVoice(value: string) {
  const voiceURI = value === '__auto__' ? null : value
  webSpeechVoiceURI.value = voiceURI
  setReadAloudWebSpeechVoiceURI(voiceURI)
}

function waitForPermissionDecision() {
  return new Promise<void>((resolve) => {
    const started = Date.now()
    const check = () => {
      if (desktopNotificationPermission() !== 'default' || Date.now() - started > 10_000) {
        resolve()
        return
      }
      window.setTimeout(check, 250)
    }
    check()
  })
}

async function toggleNotifications() {
  if (pending.value || blocked.value || !desktopNotificationsSupported()) return

  if (permission.value === 'granted') {
    setDesktopNotificationsEnabled(!enabled.value)
    refreshState()
    return
  }

  pending.value = true
  try {
    await Promise.race([
      requestDesktopNotificationPermission(),
      waitForPermissionDecision()
    ])
    refreshState()
  } finally {
    pending.value = false
  }
}

function updateOpen(open: boolean) {
  emit('update:open', open)
}

watch(() => props.open, (open) => {
  if (open) refreshState()
})

onMounted(() => {
  refreshState()
  const synthesis = browserSpeechSynthesis()
  if (synthesis) synthesis.addEventListener('voiceschanged', refreshBrowserVoices)
})

onBeforeUnmount(() => {
  const synthesis = browserSpeechSynthesis()
  if (synthesis) synthesis.removeEventListener('voiceschanged', refreshBrowserVoices)
})
</script>

<template>
  <UModal
    :open="open"
    title="Settings"
    description="Configure local Hermes web preferences."
    @update:open="updateOpen"
  >
    <template #body>
      <div class="space-y-5">
        <section class="space-y-3">
          <div class="space-y-1">
            <h3 class="text-sm font-medium text-highlighted">
              Read aloud
            </h3>
            <p class="text-sm text-muted">
              Choose how assistant response audio is generated from the message action button.
            </p>
          </div>

          <UFormField
            name="readAloudAutoRead"
            label="Auto-read new responses"
            description="Automatically read each assistant response aloud when it finishes."
          >
            <USwitch
              :model-value="autoReadResponses"
              @update:model-value="updateAutoReadResponses"
            />
          </UFormField>

          <UFormField name="readAloudEngine" label="Speech engine">
            <USelect
              :model-value="speechEngine"
              :items="speechEngineItems"
              value-key="value"
              class="w-full"
              @update:model-value="updateSpeechEngine"
            />
          </UFormField>

          <UFormField
            name="readAloudContentMode"
            label="What to read"
            description="Choose whether the read-aloud action should speak the full response or ask Hermes for a natural spoken version first."
          >
            <USelect
              :model-value="speechContentMode"
              :items="speechContentModeItems"
              value-key="value"
              class="w-full"
              @update:model-value="updateSpeechContentMode"
            />
          </UFormField>

          <UFormField
            name="readAloudSpeed"
            label="Reading speed"
            description="Applies to both Web Speech API and Edge TTS read-aloud."
          >
            <USelect
              :model-value="speechSpeed"
              :items="speechSpeedItems"
              value-key="value"
              class="w-full"
              @update:model-value="updateSpeechSpeed"
            />
          </UFormField>

          <UFormField
            v-if="speechEngine === 'web-speech'"
            name="webSpeechVoice"
            label="Web Speech voice"
            description="Stored only in this browser. Auto still detects the message language."
          >
            <USelect
              :model-value="selectedWebSpeechVoice"
              :items="webSpeechVoiceItems"
              value-key="value"
              class="w-full"
              @update:model-value="updateWebSpeechVoice"
            />
          </UFormField>

          <UFormField
            v-else
            name="edgeTts"
            label="Edge TTS"
            description="Uses Hermes backend TTS with automatic language detection. This is independent from the selected chat model."
          >
            <UAlert
              color="neutral"
              variant="subtle"
              title="Automatic Edge voice selection"
              description="Hermes generates the audio with Edge TTS and chooses a matching voice per message language, for example Slovak, English, Czech, German, French, Spanish, Italian, Polish, Portuguese, or Ukrainian."
            />
          </UFormField>
        </section>

        <USeparator />

        <section class="space-y-3">
          <div class="flex items-start justify-between gap-4">
            <div class="min-w-0 space-y-1">
              <h3 class="text-sm font-medium text-highlighted">
                Desktop notifications
              </h3>
              <p class="text-sm text-muted">
                Notify when a chat finishes while this browser window is hidden or unfocused.
              </p>
            </div>

            <UButton
              color="neutral"
              variant="subtle"
              size="sm"
              class="shrink-0"
              :aria-label="actionLabel"
              :loading="pending"
              :disabled="blocked || !supported"
              @click="toggleNotifications">
              <span class="inline-flex items-center gap-1.5">
                <UChip
                  :color="statusChipColor"
                  size="sm"
                  standalone
                />
                <span>{{ statusLabel }}</span>
              </span>
            </UButton>
          </div>

          <UAlert
            v-if="blocked"
            color="warning"
            variant="subtle"
            title="Notifications are blocked"
            description="Enable notifications for this site in your browser or macOS settings, then reopen this modal."
          />

          <UAlert
            v-else-if="!supported"
            color="neutral"
            variant="subtle"
            title="Notifications are not supported"
            description="This browser does not expose desktop notifications to the web app."
          />

        </section>
      </div>
    </template>
  </UModal>
</template>
