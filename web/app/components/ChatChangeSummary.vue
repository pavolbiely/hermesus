<script setup lang="ts">
import type { WebChatPatch, WebChatWorkspaceChanges } from '~/types/web-chat'

type FileChange = WebChatWorkspaceChanges['files'][number]
type PatchFile = WebChatPatch['files'][number]

const props = defineProps<{
  changes: WebChatWorkspaceChanges
}>()

const open = ref(true)
const expandedFiles = ref<Set<string>>(new Set())

const changedFiles = computed(() => props.changes.files)
const patchByPath = computed(() => {
  const patches = new Map<string, PatchFile>()
  for (const file of props.changes.patch?.files || []) patches.set(file.path, file)
  return patches
})

const totalLabel = computed(() => {
  const count = props.changes.totalFiles
  return `${count} ${count === 1 ? 'file' : 'files'} changed`
})

function statusLabel(status: FileChange['status']) {
  return {
    created: 'Created',
    edited: 'Modified',
    deleted: 'Deleted',
    renamed: 'Renamed',
    copied: 'Copied'
  }[status] || 'Modified'
}

function statusClass(status: FileChange['status']) {
  return {
    created: 'text-success',
    edited: 'text-dimmed',
    deleted: 'text-error',
    renamed: 'text-warning',
    copied: 'text-info'
  }[status] || 'text-dimmed'
}

function fileKey(file: FileChange) {
  return file.path
}

function isExpanded(file: FileChange) {
  return expandedFiles.value.has(fileKey(file))
}

function toggleFile(file: FileChange) {
  const next = new Set(expandedFiles.value)
  const key = fileKey(file)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedFiles.value = next
}

function patchFor(file: FileChange) {
  return patchByPath.value.get(file.path)
}

function diffLines(file: FileChange) {
  const patch = patchFor(file)?.patch
  return patch ? patch.split('\n') : []
}

function diffLineClass(line: string) {
  if (line.startsWith('+++') || line.startsWith('---')) return 'text-dimmed'
  if (line.startsWith('+')) return 'bg-success/10 text-success'
  if (line.startsWith('-')) return 'bg-error/10 text-error'
  if (line.startsWith('@@')) return 'bg-muted text-info'
  if (line.startsWith('diff --git') || line.startsWith('new file mode')) return 'text-dimmed'
  return 'text-muted'
}
</script>

<template>
  <div v-if="changedFiles.length" class="my-3 overflow-hidden rounded-lg border border-default bg-muted/30 text-sm">
    <button
      type="button"
      class="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-muted/50"
      @click="open = !open"
    >
      <span class="flex min-w-0 items-center gap-2">
        <UIcon name="i-lucide-files" class="size-4 shrink-0 text-muted" />
        <span class="truncate font-medium text-highlighted">{{ totalLabel }}</span>
        <span class="shrink-0 tabular-nums">
          <span class="text-success">+{{ changes.totalAdditions }}</span>
          <span class="ml-1 text-error">-{{ changes.totalDeletions }}</span>
        </span>
      </span>
      <UIcon
        name="i-lucide-chevron-down"
        class="size-4 shrink-0 text-dimmed transition-transform"
        :class="{ 'rotate-180': open }"
      />
    </button>

    <div v-show="open" class="border-t border-default">
      <div v-for="file in changedFiles" :key="file.path" class="border-b border-default last:border-b-0">
        <button
          type="button"
          class="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted/40"
          @click="toggleFile(file)"
        >
          <UIcon
            name="i-lucide-chevron-right"
            class="size-3.5 shrink-0 text-dimmed transition-transform"
            :class="{ 'rotate-90': isExpanded(file) }"
          />
          <span class="w-16 shrink-0 text-xs font-medium" :class="statusClass(file.status)">{{ statusLabel(file.status) }}</span>
          <span class="min-w-0 flex-1 truncate font-mono text-xs text-primary">{{ file.path }}</span>
          <span class="shrink-0 text-xs tabular-nums">
            <span class="text-success">+{{ file.additions }}</span>
            <span class="ml-1 text-error">-{{ file.deletions }}</span>
          </span>
        </button>

        <div v-if="isExpanded(file)" class="border-t border-default bg-default">
          <div v-if="patchFor(file)?.truncated" class="border-b border-default px-3 py-2 text-xs text-warning">
            Diff truncated because it exceeded the stored size limit.
          </div>
          <pre v-if="patchFor(file)?.patch" class="max-h-96 overflow-auto py-2 text-xs leading-5"><code><span
            v-for="(line, index) in diffLines(file)"
            :key="`${file.path}-${index}`"
            class="block whitespace-pre px-3 font-mono"
            :class="diffLineClass(line)"
          >{{ line || ' ' }}</span></code></pre>
          <div v-else class="px-3 py-2 text-xs text-muted">
            Diff is not available for this file.
          </div>
        </div>
      </div>
    </div>

    <div v-if="changes.patchTruncated" class="border-t border-default px-3 py-2 text-xs text-warning">
      Some diffs were truncated because they exceeded the stored size limit.
    </div>
  </div>
</template>
