<script setup lang="ts">
defineProps<{
  title: string
  workspaceStatus?: {
    label: string
    detail?: string | null
  } | null
}>()
</script>

<template>
  <UDashboardNavbar :title="title">
    <template #trailing>
      <UTooltip v-if="workspaceStatus" :text="workspaceStatus.detail || workspaceStatus.label">
        <UBadge color="neutral" variant="subtle" icon="i-lucide-git-branch" size="sm" class="hidden max-w-64 truncate font-normal sm:inline-flex">
          {{ workspaceStatus.label }}
        </UBadge>
      </UTooltip>
    </template>

    <template #right>
      <UTooltip text="Toggle dark mode">
        <UColorModeSwitch color="neutral" size="sm" />
      </UTooltip>
    </template>
  </UDashboardNavbar>
</template>
