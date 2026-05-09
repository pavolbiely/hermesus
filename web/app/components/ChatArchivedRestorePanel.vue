<script setup lang="ts">
defineProps<{
  needsWorkspace: boolean
  workspace?: string
  workspaceOptions: Array<{ label: string, value: string }>
  workspacesLoading: boolean
  restoring: boolean
}>()

const emit = defineEmits<{
  restore: []
  'update:workspace': [workspace: string | undefined]
}>()
</script>

<template>
  <div class="rounded-xl border border-dashed border-default bg-elevated/30 px-4 py-3">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div class="min-w-0">
        <p class="text-sm font-medium text-highlighted">This chat is archived</p>
        <p class="text-xs text-muted">
          {{ needsWorkspace ? 'The original workspace no longer exists. Choose where to restore it.' : 'Restore it before sending new messages.' }}
        </p>
      </div>
      <div class="flex min-w-0 items-center gap-2">
        <USelectMenu
          v-if="needsWorkspace"
          :model-value="workspace"
          :items="workspaceOptions"
          value-key="value"
          label-key="label"
          placeholder="Choose workspace"
          size="sm"
          class="min-w-52"
          :loading="workspacesLoading"
          @update:model-value="emit('update:workspace', $event)"
        />
        <UButton
          color="neutral"
          variant="soft"
          size="sm"
          icon="i-lucide-archive-restore"
          label="Restore"
          :loading="restoring"
          @click="emit('restore')"
        />
      </div>
    </div>
  </div>
</template>
