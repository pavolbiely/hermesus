<script setup lang="ts">
import type { InteractivePrompt, InteractivePromptChoice, WebChatMessage } from '~/types/web-chat'
import { readAloudAutoReadResponsesEnabled } from '~/utils/readAloudPreferences'

const autoReadPromptIds = new Set<string>()

const props = defineProps<{
  prompt: InteractivePrompt
}>()

const api = useHermesApi()
const toast = useToast()
const { read: readAloud } = useMessageReadAloud()
const localPrompt = ref<InteractivePrompt>(props.prompt)
const submittingChoice = ref<string | null>(null)
const responseText = ref('')

watch(
  () => props.prompt,
  prompt => { localPrompt.value = prompt },
  { deep: true }
)

const isPending = computed(() => localPrompt.value.status === 'pending')
const isApproval = computed(() => localPrompt.value.kind === 'approval')
const statusLabel = computed(() => {
  if (localPrompt.value.status === 'answered') return 'Answered'
  if (localPrompt.value.status === 'expired') return 'Expired'
  if (localPrompt.value.status === 'cancelled') return 'Cancelled'
  return 'Waiting for your response'
})
const responseSummaryLabel = computed(() => {
  if (localPrompt.value.status === 'answered') return answeredLabel(localPrompt.value)
  return statusLabel.value
})
const cardClasses = computed(() => isApproval.value
  ? 'border-warning/30 bg-warning/5'
  : 'border-primary/30 bg-primary/5'
)

function choiceColor(choice: InteractivePromptChoice) {
  if (choice.style === 'error') return 'error'
  if (choice.style === 'warning') return 'warning'
  if (choice.style === 'primary') return 'primary'
  return 'neutral'
}

function choiceVariant(choice: InteractivePromptChoice) {
  return choice.style === 'primary' || choice.style === 'warning' || choice.style === 'error' ? 'solid' : 'soft'
}

function answeredLabel(prompt: InteractivePrompt) {
  const choice = prompt.choices.find(item => item.id === prompt.selectedChoice)
  if (choice) return `You selected “${choice.label}”`
  if (prompt.responseText) return 'You responded'
  return 'Answered'
}

function promptReadAloudText(prompt: InteractivePrompt) {
  return [prompt.title, prompt.description]
    .map(value => value?.trim())
    .filter(Boolean)
    .join('. ')
}

function promptReadAloudMessage(prompt: InteractivePrompt, text: string): WebChatMessage {
  return {
    id: `interactive-prompt-${prompt.id}`,
    role: 'assistant',
    parts: [{ type: 'text', text }],
    createdAt: prompt.createdAt
  }
}

function maybeAutoReadPrompt(prompt: InteractivePrompt) {
  if (prompt.status !== 'pending' || !readAloudAutoReadResponsesEnabled() || autoReadPromptIds.has(prompt.id)) return
  const text = promptReadAloudText(prompt)
  if (!text) return

  autoReadPromptIds.add(prompt.id)
  void readAloud(promptReadAloudMessage(prompt, text), { queue: true, skipReadableSummary: true })
}

watch(
  localPrompt,
  prompt => maybeAutoReadPrompt(prompt),
  { immediate: true }
)

async function respond(choice?: string) {
  const text = responseText.value.trim()
  if (!isPending.value || (!choice && !text)) return

  submittingChoice.value = choice || 'text'
  try {
    const response = await api.respondRunPrompt(localPrompt.value.runId, localPrompt.value.id, {
      choice,
      text: choice ? undefined : text
    })
    localPrompt.value = response.prompt
    responseText.value = ''
  } catch (err) {
    toast.add({
      color: 'error',
      title: 'Could not send response',
      description: getHermesErrorMessage(err, 'The prompt may no longer be pending.')
    })
  } finally {
    submittingChoice.value = null
  }
}
</script>

<template>
  <UCard :class="['my-2 border', cardClasses]" :ui="{ body: 'p-3 sm:p-3' }">
    <div class="space-y-3">
      <div class="flex items-start gap-2">
        <UIcon
          :name="isApproval ? 'i-lucide-shield-alert' : 'i-lucide-circle-help'"
          :class="['mt-0.5 size-4 shrink-0', isApproval ? 'text-warning' : 'text-primary']"
        />
        <div class="min-w-0 flex-1 space-y-1">
          <div class="flex flex-wrap items-center gap-2">
            <h3 class="text-sm font-medium text-highlighted">
              {{ localPrompt.title }}
            </h3>
            <UBadge
              size="xs"
              :color="isPending ? (isApproval ? 'warning' : 'primary') : 'neutral'"
              variant="soft"
            >
              {{ statusLabel }}
            </UBadge>
          </div>
          <p v-if="localPrompt.description" class="text-sm text-muted">
            {{ localPrompt.description }}
          </p>
        </div>
      </div>

      <UCollapsible v-if="localPrompt.detail">
        <UButton color="neutral" variant="ghost" size="xs" trailing-icon="i-lucide-chevron-down" label="Details" />
        <template #content>
          <pre class="mt-2 max-h-56 overflow-auto rounded-md bg-elevated p-3 text-xs text-toned"><code>{{ localPrompt.detail }}</code></pre>
        </template>
      </UCollapsible>

      <div v-if="isPending" class="space-y-3">
        <div v-if="localPrompt.choices.length" class="flex flex-wrap gap-2">
          <UButton
            v-for="choice in localPrompt.choices"
            :key="choice.id"
            size="sm"
            :color="choiceColor(choice)"
            :variant="choiceVariant(choice)"
            :label="choice.label"
            :loading="submittingChoice === choice.id"
            :disabled="Boolean(submittingChoice)"
            @click="respond(choice.id)"
          />
        </div>

        <form v-if="localPrompt.freeText" class="flex gap-2" @submit.prevent="respond()">
          <UInput
            v-model="responseText"
            class="min-w-0 flex-1"
            placeholder="Type your response…"
            :disabled="Boolean(submittingChoice)"
          />
          <UButton
            type="submit"
            color="primary"
            label="Send"
            :loading="submittingChoice === 'text'"
            :disabled="!responseText.trim() || Boolean(submittingChoice)"
          />
        </form>
      </div>

      <p v-else class="text-xs text-muted">
        {{ responseSummaryLabel }}<span v-if="localPrompt.answeredAt"> at {{ new Date(localPrompt.answeredAt).toLocaleTimeString() }}</span>.
      </p>
    </div>
  </UCard>
</template>
