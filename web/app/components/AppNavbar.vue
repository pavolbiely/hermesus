<script setup lang="ts">
const props = defineProps<{
  title: string
  workspaceStatus?: {
    label: string
    detail?: string | null
  } | null
  commitVisible?: boolean
  commitDisabled?: boolean
  commitLoading?: boolean
}>()

const emit = defineEmits<{
  generateCommit: []
}>()

</script>

<template>
  <UDashboardNavbar
    :title="title"
    :ui="{
      root: 'h-9 px-2.5 sm:px-3',
      left: 'gap-1',
      right: 'gap-1'
    }"
  >
    <template #trailing>
      <UTooltip v-if="workspaceStatus" :text="workspaceStatus.detail || workspaceStatus.label">
        <UBadge color="neutral" variant="subtle" icon="i-lucide-git-branch" size="sm" class="hidden max-w-64 truncate font-normal sm:inline-flex">
          {{ workspaceStatus.label }}
        </UBadge>
      </UTooltip>
    </template>

    <template #right>
      <div class="flex items-center gap-3">
        <UButton
          v-if="commitVisible"
          aria-label="Generate commit message"
          icon="i-lucide-sparkles"
          loading-icon="i-lucide-cpu"
          label="Generate commit"
          color="neutral"
          variant="ghost"
          size="sm"
          :loading="commitLoading"
          :disabled="commitDisabled || commitLoading"
          @click="emit('generateCommit')"
        />
        <UTooltip text="Toggle dark mode">
          <UColorModeSwitch color="neutral" size="sm" />
        </UTooltip>
      </div>
    </template>
  </UDashboardNavbar>
</template>
