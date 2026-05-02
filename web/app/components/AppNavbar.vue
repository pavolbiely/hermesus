<script setup lang="ts">
import { getCurrentInstance } from 'vue'
import { useHermesUpdateControls } from '~/composables/useHermesUpdateControls'

const props = defineProps<{
  title: string
  workspaceStatus?: {
    label: string
    detail?: string | null
  } | null
  commitVisible?: boolean
  commitDisabled?: boolean
  commitLoading?: boolean
  updateVisible?: boolean
  updatePending?: boolean
  updateCompleted?: boolean
  updateLabel?: string
  updateColor?: 'primary' | 'success'
  updateTitle?: string
}>()

const emit = defineEmits<{
  generateCommit: []
}>()

const updates = useHermesUpdateControls()
const vnodeProps = getCurrentInstance()?.vnode.props ?? {}

function hasProp(camelName: string, kebabName = camelName.replace(/[A-Z]/g, match => `-${match.toLowerCase()}`)) {
  return Object.prototype.hasOwnProperty.call(vnodeProps, camelName) || Object.prototype.hasOwnProperty.call(vnodeProps, kebabName)
}

const resolvedUpdateVisible = computed(() => hasProp('updateVisible') ? props.updateVisible : updates.hermes.visible.value)
const resolvedUpdatePending = computed(() => hasProp('updatePending') ? props.updatePending : updates.hermes.pending.value)
const resolvedUpdateCompleted = computed(() => hasProp('updateCompleted') ? props.updateCompleted : updates.hermes.completed.value)
const resolvedUpdateLabel = computed(() => props.updateLabel || updates.hermes.label.value)
const resolvedUpdateColor = computed(() => props.updateColor || updates.hermes.color.value)
const resolvedUpdateTitle = computed(() => props.updateTitle || updates.hermes.title.value)
const resolvedAppUpdateVisible = computed(() => updates.app.visible.value)
const resolvedAppUpdatePending = computed(() => updates.app.pending.value)
const resolvedAppUpdateCompleted = computed(() => updates.app.completed.value)
const resolvedAppUpdateLabel = computed(() => updates.app.label.value)
const resolvedAppUpdateColor = computed(() => updates.app.color.value)
const resolvedAppUpdateTitle = computed(() => updates.app.title.value)

function submitUpdate() {
  updates.hermes.update()
}

function submitAppUpdate() {
  updates.app.update()
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
        <UButton
          v-if="resolvedUpdateVisible"
          size="xs"
          variant="solid"
          icon="i-lucide-refresh-cw"
          loading-icon="i-lucide-cpu"
          :label="resolvedUpdateLabel"
          :color="resolvedUpdateColor"
          :loading="resolvedUpdatePending"
          :disabled="resolvedUpdatePending || resolvedUpdateCompleted"
          :title="resolvedUpdateTitle"
          @click="submitUpdate"
        />
        <UButton
          v-if="resolvedAppUpdateVisible"
          size="xs"
          variant="solid"
          icon="i-lucide-download"
          loading-icon="i-lucide-cpu"
          :label="resolvedAppUpdateLabel"
          :color="resolvedAppUpdateColor"
          :loading="resolvedAppUpdatePending"
          :disabled="resolvedAppUpdatePending || resolvedAppUpdateCompleted"
          :title="resolvedAppUpdateTitle"
          @click="submitAppUpdate"
        />
        <UTooltip text="Toggle dark mode">
          <UColorModeSwitch color="neutral" size="sm" />
        </UTooltip>
      </div>
    </template>
  </UDashboardNavbar>
</template>
