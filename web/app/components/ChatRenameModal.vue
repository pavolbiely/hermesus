<script setup lang="ts">
const props = defineProps<{
  open: boolean
  title: string
  pending: boolean
  canRename: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  'update:title': [value: string]
  save: []
  cancel: []
}>()

const draftTitle = computed({
  get: () => props.title,
  set: value => emit('update:title', value)
})

function updateOpen(open: boolean) {
  emit('update:open', open)
  if (!open) emit('cancel')
}
</script>

<template>
  <UModal
    :open="open"
    title="Rename chat"
    description="Choose a new name for this chat."
    @update:open="updateOpen"
  >
    <template #body>
      <form class="space-y-4" @submit.prevent="emit('save')">
        <UInput
          v-model="draftTitle"
          autofocus
          aria-label="Chat name"
          class="w-full"
          :disabled="pending"
          @keydown.esc.prevent="emit('cancel')"
        />

        <div class="flex justify-end gap-2">
          <UButton
            type="button"
            color="neutral"
            variant="ghost"
            label="Cancel"
            :disabled="pending"
            @click="emit('cancel')"
          />
          <UButton
            type="submit"
            color="primary"
            label="Rename"
            :loading="pending"
            :disabled="!canRename"
          />
        </div>
      </form>
    </template>
  </UModal>
</template>
