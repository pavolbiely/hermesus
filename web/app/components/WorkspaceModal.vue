<script setup lang="ts">
import type { WebChatWorkspace } from '~/types/web-chat'

const props = defineProps<{
  open: boolean
  editingWorkspace: WebChatWorkspace | null
  label: string
  path: string
  suggestions: string[]
  pending: boolean
  canSave: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  'update:label': [value: string]
  'update:path': [value: string]
  save: []
  cancel: []
  delete: []
}>()

const workspaceLabel = computed({
  get: () => props.label,
  set: value => emit('update:label', value)
})

const workspacePath = computed({
  get: () => props.path,
  set: value => emit('update:path', value)
})

const title = computed(() => props.editingWorkspace ? 'Edit workspace' : 'Add workspace')
const saveLabel = computed(() => props.editingWorkspace ? 'Save' : 'Add workspace')

function updateOpen(open: boolean) {
  emit('update:open', open)
  if (!open) emit('cancel')
}
</script>

<template>
  <UModal
    :open="open"
    :title="title"
    description="Give the workspace a display name and point it at a local project directory."
    @update:open="updateOpen"
  >
    <template #body>
      <form class="space-y-4" @submit.prevent="emit('save')">
        <UFormField label="Name" required>
          <UInput
            v-model="workspaceLabel"
            autofocus
            placeholder="Hermesum"
            class="w-full"
            :disabled="pending"
            @keydown.esc.prevent="emit('cancel')"
          />
        </UFormField>

        <UFormField label="Directory path" required>
          <UInput
            v-model="workspacePath"
            placeholder="/Users/pavolbiely/Sites/hermesum"
            class="w-full font-mono"
            list="workspace-directory-suggestions"
            :disabled="pending"
            @keydown.esc.prevent="emit('cancel')"
          />
          <datalist id="workspace-directory-suggestions">
            <option
              v-for="suggestion in suggestions"
              :key="suggestion"
              :value="suggestion"
            />
          </datalist>
        </UFormField>

        <div class="flex items-center justify-between gap-2">
          <UButton
            v-if="editingWorkspace"
            type="button"
            color="error"
            variant="ghost"
            label="Delete"
            :loading="pending"
            @click="emit('delete')"
          />
          <span v-else />

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
              :label="saveLabel"
              :loading="pending"
              :disabled="!canSave"
            />
          </div>
        </div>
      </form>
    </template>
  </UModal>
</template>
