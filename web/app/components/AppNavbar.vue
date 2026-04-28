<script setup lang="ts">
import type { Ref } from 'vue'

const props = defineProps<{
  title: string
  workspaceStatus?: {
    label: string
    detail?: string | null
  } | null
  updateVisible?: boolean
  updatePending?: boolean
  updateCompleted?: boolean
  updateLabel?: string
  updateColor?: 'primary' | 'success'
  updateTitle?: string
}>()

const updateControl = inject<{
  visible: Ref<boolean>
  pending: Ref<boolean>
  completed: Ref<boolean>
  label: Ref<string>
  color: Ref<'primary' | 'success'>
  title: Ref<string>
  update: () => void
} | null>('hermesUpdateControl', null)

const resolvedUpdateVisible = computed(() => props.updateVisible ?? updateControl?.visible.value ?? false)
const resolvedUpdatePending = computed(() => props.updatePending ?? updateControl?.pending.value ?? false)
const resolvedUpdateCompleted = computed(() => props.updateCompleted ?? updateControl?.completed.value ?? false)
const resolvedUpdateLabel = computed(() => props.updateLabel || updateControl?.label.value || 'Update')
const resolvedUpdateColor = computed(() => props.updateColor || updateControl?.color.value || 'primary')
const resolvedUpdateTitle = computed(() => props.updateTitle || updateControl?.title.value || 'Update Hermes')

function submitUpdate() {
  updateControl?.update()
}
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
      <UButton
        v-if="resolvedUpdateVisible"
        size="sm"
        variant="solid"
        icon="i-lucide-refresh-cw"
        :label="resolvedUpdateLabel"
        :color="resolvedUpdateColor"
        :loading="resolvedUpdatePending"
        :disabled="resolvedUpdatePending || resolvedUpdateCompleted"
        :title="resolvedUpdateTitle"
        @click="submitUpdate"
      />
      <UTooltip text="Toggle dark mode">
        <UColorModeSwitch color="neutral" size="sm" />
      </UTooltip>
    </template>
  </UDashboardNavbar>
</template>
