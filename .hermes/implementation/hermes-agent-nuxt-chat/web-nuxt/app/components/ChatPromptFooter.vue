<script setup lang="ts">
type ChatPromptFooterProps = {
  submitStatus: 'ready' | 'submitted' | 'streaming' | 'error'
  profileLabel?: string
  projectLabel?: string
  modelLabel?: string
  reasoningLabel?: string
}

const props = withDefaults(defineProps<ChatPromptFooterProps>(), {
  profileLabel: 'Hermes',
  projectLabel: 'hermesum',
  modelLabel: 'GPT-5.5',
  reasoningLabel: 'medium'
})

const emit = defineEmits<{
  stop: []
}>()

const mockButtons = [
  { label: 'Attach file', icon: 'i-lucide-paperclip' },
  { label: 'Dictate by voice', icon: 'i-lucide-mic' }
]

const selectors = computed(() => [
  { label: props.profileLabel, icon: 'i-lucide-user-round', ariaLabel: 'Hermes profile' },
  { label: props.projectLabel, icon: 'i-lucide-folder', ariaLabel: 'Project or directory' },
  { label: props.modelLabel, icon: 'i-lucide-cpu', ariaLabel: 'Model' },
  { label: props.reasoningLabel, icon: 'i-lucide-brain', ariaLabel: 'Reasoning effort' }
])
</script>

<template>
  <div class="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden">
    <UTooltip v-for="button in mockButtons" :key="button.label" :text="`${button.label} (coming soon)`">
      <UButton
        :aria-label="`${button.label} (coming soon)`"
        :icon="button.icon"
        color="neutral"
        variant="ghost"
        size="sm"
        disabled
      />
    </UTooltip>

    <USeparator orientation="vertical" class="mx-1 h-5" />

    <div class="flex min-w-0 items-center gap-1.5 overflow-x-auto">
      <UButton
        v-for="selector in selectors"
        :key="selector.ariaLabel"
        :aria-label="selector.ariaLabel"
        :icon="selector.icon"
        trailing-icon="i-lucide-chevron-down"
        color="neutral"
        variant="ghost"
        size="sm"
        class="shrink-0"
        disabled
      >
        {{ selector.label }}
      </UButton>
    </div>
  </div>

  <UChatPromptSubmit :status="submitStatus" @stop="emit('stop')" />
</template>
