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
const resolvedUpdateCommits = computed(() => updates.hermes.commits.value)
const resolvedUpdateHasMoreCommits = computed(() => updates.hermes.hasMoreCommits.value)
const resolvedUpdateCompareUrl = computed(() => updates.hermes.compareUrl.value)
const resolvedUpdateRevisionSummary = computed(() => updates.hermes.revisionSummary.value)
const resolvedUpdatePopoverMessage = computed(() => updates.hermes.popoverMessage.value)
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
        <UPopover
          v-if="resolvedUpdateVisible"
          mode="hover"
          :open-delay="350"
          :content="{ side: 'bottom', align: 'end', sideOffset: 8 }"
          :ui="{ content: 'w-[31rem] p-0' }"
        >
          <UButton
            size="xs"
            variant="solid"
            icon="i-lucide-refresh-cw"
            loading-icon="i-lucide-cpu"
            :label="resolvedUpdateLabel"
            :color="resolvedUpdateColor"
            :loading="resolvedUpdatePending"
            :disabled="resolvedUpdatePending || resolvedUpdateCompleted"
            @click="submitUpdate"
          />

          <template #content>
            <div class="w-[31rem] space-y-3 p-3 text-left text-xs leading-relaxed">
              <div class="space-y-1 border-b border-default pb-2">
                <div class="flex items-center justify-between gap-3">
                  <div class="min-w-0 font-medium text-highlighted">{{ resolvedUpdateTitle }}</div>
                  <a
                    v-if="resolvedUpdateCompareUrl"
                    :href="resolvedUpdateCompareUrl"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="inline-flex shrink-0 items-center gap-1 text-primary hover:underline"
                  >
                    GitHub
                    <UIcon name="i-lucide-external-link" class="size-3" />
                  </a>
                </div>
                <div v-if="resolvedUpdateRevisionSummary" class="text-muted">
                  {{ resolvedUpdateRevisionSummary }}
                </div>
              </div>

              <div v-if="resolvedUpdateCommits.length" class="space-y-2">
                <div class="divide-y divide-default/60 rounded-md border border-default/70 bg-muted/40 dark:bg-muted/20">
                  <component
                    :is="commit.url ? 'a' : 'div'"
                    v-for="commit in resolvedUpdateCommits"
                    :key="commit.hash"
                    :href="commit.url || undefined"
                    :target="commit.url ? '_blank' : undefined"
                    :rel="commit.url ? 'noopener noreferrer' : undefined"
                    class="group flex min-w-0 items-center gap-2 px-2 py-1.5"
                    :class="commit.url ? 'transition hover:bg-primary/5' : ''"
                  >
                    <code class="shrink-0 font-mono text-[10px] leading-4" :class="commit.url ? 'text-primary' : 'text-muted'">{{ commit.shortHash }}</code>
                    <span class="min-w-0 flex-1 truncate text-highlighted" :class="commit.url ? 'group-hover:underline' : ''">
                      {{ commit.subject }}
                    </span>
                    <span v-if="commit.formattedCommittedAt" class="hidden shrink-0 text-[10px] leading-4 text-muted sm:inline">
                      {{ commit.formattedCommittedAt }}
                    </span>
                    <UIcon v-if="commit.url" name="i-lucide-external-link" class="size-3 shrink-0 text-muted opacity-70" />
                  </component>
                </div>
                <div v-if="resolvedUpdateHasMoreCommits" class="text-muted">
                  And more commits are included.
                </div>
              </div>

              <div v-else class="text-muted">
                {{ resolvedUpdatePopoverMessage }}
              </div>
            </div>
          </template>
        </UPopover>
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
