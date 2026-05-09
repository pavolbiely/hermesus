<script setup lang="ts">
const open = defineModel<boolean>('open', { required: true })
const message = defineModel<string>('message', { required: true })

defineProps<{
  copied: boolean
}>()

const emit = defineEmits<{
  copy: []
}>()
</script>

<template>
  <UModal
    v-model:open="open"
    title="Generated commit message"
    description="Review the generated message before copying it."
    :ui="{ content: 'sm:max-w-lg' }"
  >
    <template #body>
      <div class="space-y-3">
        <UTextarea
          v-model="message"
          readonly
          :rows="14"
          class="w-full font-mono text-sm"
          aria-label="Generated commit message"
        />
      </div>
    </template>

    <template #footer>
      <div class="flex w-full justify-between gap-2">
        <UButton
          color="neutral"
          variant="ghost"
          label="Close"
          @click="open = false"
        />
        <UButton
          color="neutral"
          icon="i-lucide-copy"
          :label="copied ? 'Copied' : 'Copy'"
          @click="emit('copy')"
        />
      </div>
    </template>
  </UModal>
</template>
