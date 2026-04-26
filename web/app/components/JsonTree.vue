<script setup lang="ts">
type JsonPrimitive = string | number | boolean | null

type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue }

type JsonEntry = {
  key: string
  value: JsonValue
}

const props = withDefaults(defineProps<{
  value: unknown
  depth?: number
  path?: string
  defaultExpandedDepth?: number
  label?: string
  wrapLines?: boolean
}>(), {
  depth: 0,
  path: 'root',
  defaultExpandedDepth: 3,
  label: undefined,
  wrapLines: false
})

const collapsed = ref(props.depth >= props.defaultExpandedDepth)

const normalizedValue = computed(() => normalizeJsonValue(props.value))
const isArray = computed(() => Array.isArray(normalizedValue.value))
const isObject = computed(() => isPlainObject(normalizedValue.value))
const isBranch = computed(() => isArray.value || isObject.value)
const entries = computed<JsonEntry[]>(() => {
  const value = normalizedValue.value
  if (Array.isArray(value)) {
    return value.map((item, index) => ({ key: String(index), value: item }))
  }

  if (isPlainObject(value)) {
    return Object.entries(value).map(([key, entryValue]) => ({ key, value: normalizeJsonValue(entryValue) }))
  }

  return []
})

const bracketPair = computed(() => isArray.value ? ['[', ']'] : ['{', '}'])
const summary = computed(() => {
  const count = entries.value.length
  return `${count} ${count === 1 ? 'item' : 'items'}`
})

watch(
  () => props.value,
  () => {
    collapsed.value = props.depth >= props.defaultExpandedDepth
  }
)

function normalizeJsonValue(value: unknown): JsonValue {
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (trimmed && ['{', '['].includes(trimmed[0] || '')) {
      try {
        return normalizeJsonValue(JSON.parse(trimmed))
      } catch {
        return value
      }
    }

    return value
  }

  if (value === null) return null
  if (typeof value === 'number' || typeof value === 'boolean') return value
  if (Array.isArray(value)) return value.map(normalizeJsonValue)
  if (isPlainObject(value)) {
    return Object.fromEntries(Object.entries(value).map(([key, entryValue]) => [key, normalizeJsonValue(entryValue)]))
  }

  if (value === undefined) return null
  return String(value)
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function primitiveClass(value: JsonValue) {
  if (typeof value === 'string') return 'text-success'
  if (typeof value === 'number') return 'text-info'
  if (typeof value === 'boolean') return 'text-warning'
  if (value === null) return 'text-dimmed'
  return 'text-highlighted'
}

function primitiveText(value: JsonValue) {
  return typeof value === 'string' ? JSON.stringify(value) : String(value)
}

function childPath(key: string) {
  return `${props.path}.${key}`
}
</script>

<template>
  <div class="font-mono text-xs leading-5 text-highlighted" :class="wrapLines ? 'whitespace-normal' : 'whitespace-nowrap'">
    <div class="flex items-start gap-1">
      <span v-if="label !== undefined" class="shrink-0 text-primary">{{ JSON.stringify(label) }}:</span>

      <template v-if="isBranch">
        <button
          type="button"
          class="mt-0.5 inline-flex size-3.5 shrink-0 items-center justify-center rounded text-dimmed transition-colors hover:bg-muted hover:text-default"
          :aria-expanded="!collapsed"
          @click="collapsed = !collapsed"
        >
          <UIcon :name="collapsed ? 'i-lucide-plus' : 'i-lucide-minus'" class="size-3" />
        </button>

        <div class="min-w-0 flex-1">
          <button
            type="button"
            class="text-left text-highlighted transition-colors hover:text-default"
            :aria-expanded="!collapsed"
            @click="collapsed = !collapsed"
          >
            <span>{{ bracketPair[0] }}</span>
            <span v-if="collapsed" class="text-dimmed"> … {{ summary }} </span>
            <span v-if="collapsed">{{ bracketPair[1] }}</span>
          </button>

          <div v-if="!collapsed" class="ml-2 border-l border-default/50 pl-2">
            <JsonTree
              v-for="entry in entries"
              :key="childPath(entry.key)"
              :value="entry.value"
              :label="entry.key"
              :path="childPath(entry.key)"
              :depth="depth + 1"
              :default-expanded-depth="defaultExpandedDepth"
              :wrap-lines="wrapLines"
            />
            <div class="text-highlighted">{{ bracketPair[1] }}</div>
          </div>
        </div>
      </template>

      <span
        v-else
        class="min-w-0"
        :class="[primitiveClass(normalizedValue), wrapLines ? 'break-words' : 'whitespace-nowrap']"
      >
        {{ primitiveText(normalizedValue) }}
      </span>
    </div>
  </div>
</template>
