<script setup lang="ts">
defineProps<{
  title: string
}>()
</script>

<template>
  <UDashboardNavbar :title="title">
    <template #right>
      <UTooltip text="Toggle dark mode">
        <UColorModeSwitch color="neutral" size="sm" />
      </UTooltip>
    </template>
  </UDashboardNavbar>
</template>
