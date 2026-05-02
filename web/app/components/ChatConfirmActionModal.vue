<script setup lang="ts">
const props = defineProps<{
  open: boolean
  action: 'duplicate' | 'archive' | 'delete' | null
  title: string
  description: string
  pending: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  confirm: []
  cancel: []
}>()

const confirmColor = computed(() => props.action === 'delete' ? 'error' : 'primary')
const confirmLabel = computed(() => {
  if (props.action === 'delete') return 'Delete'
  if (props.action === 'archive') return 'Archive'
  return 'Duplicate'
})

function updateOpen(open: boolean) {
  emit('update:open', open)
  if (!open) emit('cancel')
}
</script>

<template>
  <UModal
    :open="open"
    :title="title"
    :description="description"
    @update:open="updateOpen"
  >
    <template #footer>
      <div class="flex w-full justify-end gap-2">
        <UButton
          type="button"
          color="neutral"
          variant="ghost"
          label="Cancel"
          :disabled="pending"
          @click="emit('cancel')"
        />
        <UButton
          type="button"
          :color="confirmColor"
          :label="confirmLabel"
          :loading="pending"
          @click="emit('confirm')"
        />
      </div>
    </template>
  </UModal>
</template>
