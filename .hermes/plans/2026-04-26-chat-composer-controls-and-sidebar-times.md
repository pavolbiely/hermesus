# Chat Composer Controls and Sidebar Times Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add mock attachment/dictation controls plus profile/project/model/reasoning selectors to the Nuxt chat composer, and show Codex-style relative last-activity times in the left sidebar.

**Architecture:** Keep this UI-only first pass small and local to the existing Nuxt prototype. Reuse Nuxt UI components and `UChatPrompt` slots instead of replacing the prompt internals. Sidebar timestamps should use the already exposed `WebChatSession.updatedAt` value from `/api/web-chat/sessions`.

**Tech Stack:** Nuxt 4, Vue 3 `<script setup>`, TypeScript, Nuxt UI 4, Lucide icons via `UIcon`.

---

## Context

Current relevant files:

- Chat prompt in new chat page: `.hermes/implementation/hermes-agent-nuxt-chat/web-nuxt/app/pages/index.vue`
- Chat prompt in existing chat page: `.hermes/implementation/hermes-agent-nuxt-chat/web-nuxt/app/pages/chat/[id].vue`
- Sidebar session list: `.hermes/implementation/hermes-agent-nuxt-chat/web-nuxt/app/layouts/default.vue`
- Web chat types: `.hermes/implementation/hermes-agent-nuxt-chat/web-nuxt/app/types/web-chat.ts`
- API already returns `updatedAt`: `.hermes/implementation/hermes-agent-nuxt-chat/backend/hermes_cli/web_chat.py`

Nuxt UI `UChatPrompt` supports `#header` and `#footer` slots. Use `#footer` for the new controls:

```vue
<UChatPrompt v-model="input" :error="error" @submit="onSubmit">
  <template #footer>
    <!-- left controls + submit button -->
  </template>
</UChatPrompt>
```

The screenshot target layout is:

- lower-left prompt controls: paperclip, microphone, divider
- then chips/selectors: Hermes profile, project/directory, model, reasoning
- submit/stop stays at the right
- sidebar chat rows show right-aligned relative time like `7h`, `2d`, `4d`

Non-goals for this pass:

- Real file upload implementation
- Real voice dictation implementation
- Persisting selected profile/project/model/reasoning
- Backend model/reasoning routing changes
- Grouping sidebar sessions by project

---

## Acceptance Criteria

1. Both the new-chat prompt and existing-chat prompt render the same footer controls.
2. Attachment and dictation buttons are visible mock buttons, disabled or no-op, with accessible labels/tooltips.
3. Profile, project/directory, model, and reasoning controls are visible chips matching the requested order.
4. Existing submit and stop behavior still works.
5. Sidebar session rows show a compact relative last-written time based on `session.updatedAt`.
6. Sidebar title truncation still works and timestamps remain right-aligned.
7. `npm run typecheck` passes in `web-nuxt`.
8. Backend web chat tests still pass if backend is touched; this plan should not require backend changes.

---

## Task 1: Create shared prompt footer component

**Objective:** Avoid duplicating composer footer markup in both chat pages.

**Files:**

- Create: `.hermes/implementation/hermes-agent-nuxt-chat/web-nuxt/app/components/ChatPromptFooter.vue`
- Modify later: `app/pages/index.vue`, `app/pages/chat/[id].vue`

**Step 1: Create component with mock controls**

Create `app/components/ChatPromptFooter.vue`:

```vue
<script setup lang="ts">
type ChatPromptFooterProps = {
  submitStatus: 'ready' | 'submitted' | 'streaming' | 'error'
  profileLabel?: string
  projectLabel?: string
  modelLabel?: string
  reasoningLabel?: string
}

withDefaults(defineProps<ChatPromptFooterProps>(), {
  profileLabel: 'Hermes',
  projectLabel: 'hermesum',
  modelLabel: 'GPT-5.5',
  reasoningLabel: 'medium'
})

const emit = defineEmits<{
  stop: []
}>()

const mockButtons = [
  { label: 'Attach file', icon: 'i-lucide-paperclip' },
  { label: 'Dictate by voice', icon: 'i-lucide-mic' }
]

const selectors = computed(() => [
  { label: profileLabel.value, icon: 'i-lucide-user-round', ariaLabel: 'Hermes profile' },
  { label: projectLabel.value, icon: 'i-lucide-folder', ariaLabel: 'Project or directory' },
  { label: modelLabel.value, icon: 'i-lucide-cpu', ariaLabel: 'Model' },
  { label: reasoningLabel.value, icon: 'i-lucide-brain', ariaLabel: 'Reasoning effort' }
])
```

Important: Vue props from `withDefaults` are not refs when destructured this way unless using reactive destructure support. Prefer the simpler implementation below to avoid mistakes:

```vue
<script setup lang="ts">
type ChatPromptFooterProps = {
  submitStatus: 'ready' | 'submitted' | 'streaming' | 'error'
  profileLabel?: string
  projectLabel?: string
  modelLabel?: string
  reasoningLabel?: string
}

const props = withDefaults(defineProps<ChatPromptFooterProps>(), {
  profileLabel: 'Hermes',
  projectLabel: 'hermesum',
  modelLabel: 'GPT-5.5',
  reasoningLabel: 'medium'
})

const emit = defineEmits<{
  stop: []
}>()

const mockButtons = [
  { label: 'Attach file', icon: 'i-lucide-paperclip' },
  { label: 'Dictate by voice', icon: 'i-lucide-mic' }
]

const selectors = computed(() => [
  { label: props.profileLabel, icon: 'i-lucide-user-round', ariaLabel: 'Hermes profile' },
  { label: props.projectLabel, icon: 'i-lucide-folder', ariaLabel: 'Project or directory' },
  { label: props.modelLabel, icon: 'i-lucide-cpu', ariaLabel: 'Model' },
  { label: props.reasoningLabel, icon: 'i-lucide-brain', ariaLabel: 'Reasoning effort' }
])
</script>

<template>
  <div class="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden">
    <UTooltip v-for="button in mockButtons" :key="button.label" :text="`${button.label} (coming soon)`">
      <UButton
        :aria-label="`${button.label} (coming soon)`"
        :icon="button.icon"
        color="neutral"
        variant="ghost"
        size="sm"
        disabled
      />
    </UTooltip>

    <USeparator orientation="vertical" class="mx-1 h-5" />

    <div class="flex min-w-0 items-center gap-1.5 overflow-x-auto">
      <UButton
        v-for="selector in selectors"
        :key="selector.ariaLabel"
        :aria-label="selector.ariaLabel"
        :icon="selector.icon"
        trailing-icon="i-lucide-chevron-down"
        color="neutral"
        variant="ghost"
        size="sm"
        class="shrink-0"
        disabled
      >
        {{ selector.label }}
      </UButton>
    </div>
  </div>

  <UChatPromptSubmit :status="submitStatus" @stop="emit('stop')" />
</template>
```

**Step 2: Typecheck the component after creation**

Run from `web-nuxt`:

```bash
npm run typecheck
```

Expected: either pass, or errors only if the copied status union does not match Nuxt UI. If status union errors, inspect `ChatPromptSubmit.vue.d.ts` and adjust `submitStatus` to the exact Nuxt UI type.

**Step 3: Commit after successful integration, not yet**

Do not commit after this task alone unless the component is already used; unused component is acceptable temporarily but better to commit after Task 2.

---

## Task 2: Use shared prompt footer in both chat pages

**Objective:** Render the same composer controls on new-chat and existing-chat pages.

**Files:**

- Modify: `.hermes/implementation/hermes-agent-nuxt-chat/web-nuxt/app/pages/index.vue`
- Modify: `.hermes/implementation/hermes-agent-nuxt-chat/web-nuxt/app/pages/chat/[id].vue`

**Step 1: Update new chat prompt**

Replace the existing prompt body in `app/pages/index.vue`:

```vue
<UChatPrompt v-model="input" :error="error" @submit="onSubmit">
  <UChatPromptSubmit :status="loading ? 'submitted' : 'ready'" />
</UChatPrompt>
```

with:

```vue
<UChatPrompt v-model="input" :error="error" @submit="onSubmit">
  <template #footer>
    <ChatPromptFooter :submit-status="loading ? 'submitted' : 'ready'" />
  </template>
</UChatPrompt>
```

**Step 2: Update existing chat prompt**

Replace the existing footer prompt in `app/pages/chat/[id].vue`:

```vue
<UChatPrompt v-model="input" :error="error" @submit="onSubmit">
  <UChatPromptSubmit :status="chatStatus" @stop="runStream.stop" />
</UChatPrompt>
```

with:

```vue
<UChatPrompt v-model="input" :error="error" @submit="onSubmit">
  <template #footer>
    <ChatPromptFooter :submit-status="chatStatus" @stop="runStream.stop" />
  </template>
</UChatPrompt>
```

**Step 3: Verify typecheck**

Run:

```bash
cd .hermes/implementation/hermes-agent-nuxt-chat/web-nuxt
npm run typecheck
```

Expected: pass.

**Step 4: Manual browser check**

Run if needed:

```bash
cd .hermes/implementation/hermes-agent-nuxt-chat/web-nuxt
npm run dev
```

Open `http://127.0.0.1:3019` and verify:

- new chat composer shows attachment, mic, profile, project, model, reasoning, submit
- existing chat composer shows same controls
- pressing Enter still submits
- clicking submit still submits
- stop button still appears while streaming

**Step 5: Commit**

```bash
git -C .hermes/implementation/hermes-agent-nuxt-chat add web-nuxt/app/components/ChatPromptFooter.vue web-nuxt/app/pages/index.vue web-nuxt/app/pages/chat/[id].vue
git -C .hermes/implementation/hermes-agent-nuxt-chat commit -m "feat: add chat composer mock controls"
```

---

## Task 3: Add relative time formatter composable

**Objective:** Centralize compact `7h` / `2d` sidebar time formatting.

**Files:**

- Create: `.hermes/implementation/hermes-agent-nuxt-chat/web-nuxt/app/composables/useRelativeTime.ts`

**Step 1: Create formatter**

Create `app/composables/useRelativeTime.ts`:

```ts
const SECOND = 1000
const MINUTE = 60 * SECOND
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR
const WEEK = 7 * DAY
const MONTH = 30 * DAY
const YEAR = 365 * DAY

export function formatCompactRelativeTime(value: string | Date, now = new Date()) {
  const date = value instanceof Date ? value : new Date(value)
  const timestamp = date.getTime()

  if (!Number.isFinite(timestamp)) return ''

  const diff = Math.max(0, now.getTime() - timestamp)

  if (diff < MINUTE) return 'now'
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}m`
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h`
  if (diff < WEEK) return `${Math.floor(diff / DAY)}d`
  if (diff < MONTH) return `${Math.floor(diff / WEEK)}w`
  if (diff < YEAR) return `${Math.floor(diff / MONTH)}mo`

  return `${Math.floor(diff / YEAR)}y`
}
```

**Step 2: Add lightweight tests if a test runner exists**

This prototype currently has no frontend test script in `package.json`. Do not add Vitest just for this. Rely on `npm run typecheck` and manual visual checks.

**Step 3: Verify typecheck**

Run:

```bash
cd .hermes/implementation/hermes-agent-nuxt-chat/web-nuxt
npm run typecheck
```

Expected: pass.

---

## Task 4: Replace sidebar navigation menu with custom rows containing timestamps

**Objective:** `UNavigationMenu` item API does not naturally expose a right-aligned timestamp slot here, so use simple Nuxt UI-native primitives for the session list.

**Files:**

- Modify: `.hermes/implementation/hermes-agent-nuxt-chat/web-nuxt/app/layouts/default.vue`

**Step 1: Keep `New chat` simple**

In `default.vue`, remove the `items` computed and replace it with:

```ts
const sessions = computed(() => data.value?.sessions || [])
```

**Step 2: Add timestamp helper**

Add in `<script setup>`:

```ts
const now = useNow({ interval: 60_000 })

function sessionTime(updatedAt: string) {
  return formatCompactRelativeTime(updatedAt, now.value)
}
```

If `useNow` is not auto-imported in this Nuxt setup, import it:

```ts
import { useNow } from '@vueuse/core'
```

Nuxt UI already depends on VueUse, but if direct import is not available from app code, use a local timer instead:

```ts
const now = ref(new Date())
let timer: ReturnType<typeof setInterval> | undefined

onMounted(() => {
  timer = setInterval(() => {
    now.value = new Date()
  }, 60_000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
```

Prefer the no-new-dependency local timer if `@vueuse/core` is not declared for this app.

**Step 3: Replace `UNavigationMenu` template**

Replace:

```vue
<UNavigationMenu :items="items" orientation="vertical" class="px-2" />
```

with:

```vue
<nav class="space-y-1 px-2" aria-label="Chat sessions">
  <UButton
    to="/"
    icon="i-lucide-plus"
    label="New chat"
    color="neutral"
    variant="ghost"
    block
    class="justify-start"
  />

  <div class="pt-2">
    <NuxtLink
      v-for="session in sessions"
      :key="session.id"
      :to="`/chat/${session.id}`"
      class="flex min-w-0 items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-elevated"
      :class="route.params.id === session.id ? 'bg-elevated text-highlighted' : 'text-default'"
    >
      <UIcon name="i-lucide-message-square" class="size-4 shrink-0 text-muted" />
      <span class="min-w-0 flex-1 truncate">
        {{ session.title || session.preview || 'Untitled chat' }}
      </span>
      <span class="shrink-0 text-xs text-muted" :title="new Date(session.updatedAt).toLocaleString()">
        {{ sessionTime(session.updatedAt) }}
      </span>
    </NuxtLink>
  </div>
</nav>
```

**Step 4: Verify typecheck**

Run:

```bash
cd .hermes/implementation/hermes-agent-nuxt-chat/web-nuxt
npm run typecheck
```

Expected: pass.

**Step 5: Manual browser check**

Verify:

- left sidebar still has `New chat`
- sessions navigate correctly
- active chat row is highlighted
- timestamp appears at far right and title truncates before it
- invalid/missing dates render no timestamp rather than `NaN`

**Step 6: Commit**

```bash
git -C .hermes/implementation/hermes-agent-nuxt-chat add web-nuxt/app/composables/useRelativeTime.ts web-nuxt/app/layouts/default.vue
git -C .hermes/implementation/hermes-agent-nuxt-chat commit -m "feat: show relative chat activity times"
```

---

## Task 5: Optional polish after first visual pass

**Objective:** Match the screenshot more closely without expanding scope.

**Files:**

- Modify only if needed: `app/components/ChatPromptFooter.vue`
- Modify only if needed: `app/layouts/default.vue`

**Checklist:**

- If disabled mock controls look too muted, change buttons from `disabled` to no-op `@click.prevent` and add `aria-disabled="true"` while keeping visual opacity normal.
- If prompt footer wraps poorly on narrow widths, hide selector labels under small breakpoints or allow horizontal scroll only for selector chips.
- If `Hermes` profile label should be lowercase/instance-specific, set `profileLabel="hermesum"` at call sites.
- If project/directory should show the current workspace basename, derive it later from backend/config; keep static for mock pass.

**Verification:**

```bash
cd .hermes/implementation/hermes-agent-nuxt-chat/web-nuxt
npm run typecheck
npm run build
```

Expected: pass.

---

## Task 6: Final verification

**Objective:** Confirm the implementation did not regress chat behavior.

**Commands:**

Frontend:

```bash
cd .hermes/implementation/hermes-agent-nuxt-chat/web-nuxt
npm run typecheck
npm run build
```

Backend, only if backend files changed:

```bash
cd .hermes/implementation/hermes-agent-nuxt-chat/backend
python -m pytest tests/hermes_cli/test_web_chat.py
```

Manual QA:

1. Start dev server with `npm run dev` in `web-nuxt`.
2. Open `http://127.0.0.1:3019`.
3. Create a new chat.
4. Confirm submit creates/navigates to a chat session.
5. Confirm sidebar list refreshes and the new session shows `now` or `1m`.
6. Send another message in an existing chat.
7. Confirm that session's sidebar timestamp updates after the run finishes.
8. Confirm mock attachment/dictation/selector buttons do not accidentally submit the form.

Final commit if Task 5 made changes:

```bash
git -C .hermes/implementation/hermes-agent-nuxt-chat status --short
git -C .hermes/implementation/hermes-agent-nuxt-chat add web-nuxt/app/components/ChatPromptFooter.vue web-nuxt/app/layouts/default.vue
git -C .hermes/implementation/hermes-agent-nuxt-chat commit -m "polish: refine chat composer controls"
```

---

## Notes and Risks

- `UChatPromptSubmit` status type should be confirmed by typecheck; if Nuxt UI accepts only a narrower union, adjust `ChatPromptFooterProps.submitStatus` accordingly.
- `updatedAt` currently comes from `last_active` or `started_at`, already serialized by backend. No backend API change is needed.
- Replacing `UNavigationMenu` with custom rows is acceptable here because the timestamp layout requires a trailing element; keep the markup simple and accessible.
- Keep attachment and dictation as explicit mock/no-op controls so users do not assume files or audio are supported yet.
