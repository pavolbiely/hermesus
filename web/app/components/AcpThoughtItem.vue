<script setup lang="ts">
import { useScrollShadow } from '@nuxt/ui/composables'

const props = defineProps<{
  text?: string
  detail?: string
}>()

const open = ref(false)
const thoughtScrollContainer = ref<HTMLElement | null>(null)
const { style: thoughtScrollShadowStyle } = useScrollShadow(thoughtScrollContainer)
const normalizedText = computed(() => props.text?.trim() || '')
const detailText = computed(() => props.detail?.trim() || '')
const preview = computed(() => normalizedText.value
  ? normalizedText.value.split(/\s+/).slice(0, 12).join(' ')
  : detailText.value)
const bodyText = computed(() => normalizedText.value || detailText.value)
</script>

<template>
  <UCollapsible v-if="bodyText" v-model:open="open">
    <button
      type="button"
      class="group flex w-full max-w-full items-center gap-1.5 overflow-hidden text-left text-sm text-muted transition-colors hover:text-default"
    >
      <UIcon
        :name="open ? 'i-lucide-chevron-down' : 'i-lucide-chevron-right'"
        class="size-3.5 shrink-0 text-dimmed"
      />
      <UIcon name="i-lucide-sparkles" class="size-3.5 shrink-0 text-dimmed" />
      <span class="shrink-0 font-medium text-toned">Thoughts</span>
      <UTooltip :text="preview" :delay-duration="250">
        <span class="block min-w-0 truncate text-dimmed">
          {{ preview }}
        </span>
      </UTooltip>
    </button>

    <template #content>
      <div
        ref="thoughtScrollContainer"
        class="mt-2 max-h-[220px] overflow-y-auto rounded-md bg-muted/20 px-3 py-2"
        :style="thoughtScrollShadowStyle"
      >
        <Comark
          :markdown="bodyText"
          class="chat-reasoning-markdown text-sm text-muted"
        />
      </div>
    </template>
  </UCollapsible>
</template>
