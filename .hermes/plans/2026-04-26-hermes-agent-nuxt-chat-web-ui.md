# Hermes Agent Nuxt Chat Web UI Implementation Proposal

**Goal:** Replace or complement the current React/xterm chat dashboard with a native Nuxt 4 + Nuxt UI chat interface inspired by `nuxt-ui-templates/chat`.

**Reference cloned:** `.hermes/vendor/nuxt-ui-chat-template` from `https://github.com/nuxt-ui-templates/chat.git`.

## Current Hermes facts inspected

- Hermes Agent v0.11.0 is installed from `/Users/pavolbiely/.hermes/hermes-agent`.
- Current web dashboard is React/Vite under `web/`.
- `web/src/pages/ChatPage.tsx` embeds `hermes --tui` in xterm via `WebSocket /api/pty`.
- Backend is `hermes_cli/web_server.py` FastAPI, serving built assets and dashboard REST APIs.
- Existing OpenAI-compatible agent API lives in `gateway/platforms/api_server.py`:
  - `POST /v1/chat/completions`
  - `POST /v1/responses`
  - `POST /v1/runs`
  - `GET /v1/runs/{run_id}/events` SSE
  - `POST /v1/runs/{run_id}/stop`
- Dashboard auth uses an ephemeral `X-Hermes-Session-Token`, injected into SPA HTML.

## Template facts inspected

Useful Nuxt UI template pieces:

- `app/layouts/default.vue`: `UDashboardGroup`, `UDashboardSidebar`, searchable chat history.
- `app/pages/index.vue`: new-chat landing prompt.
- `app/pages/chat/[id].vue`: `UChatMessages`, `UChatPrompt`, `UChatPromptSubmit`, streaming transport.
- `app/components/chat/message/MessageContent.vue`: renders text, reasoning, tool parts.
- `server/api/chats*.ts`: CRUD + streaming endpoint pattern.
- `server/db/schema.ts`: simple `chats`, `messages`, `votes` schema.

## Recommended architecture

Do **not** route the Nuxt UI through xterm/PTY. Build a first-class web chat protocol on top of Hermes backend events.

```text
Nuxt app
  ├─ UDashboardSidebar: sessions, config, logs, tools, cron
  ├─ /chat: new prompt
  ├─ /chat/:id: conversation view
  └─ server/api/*: thin proxy to Hermes FastAPI when needed

Hermes FastAPI (`hermes_cli/web_server.py`)
  ├─ dashboard REST APIs (existing)
  ├─ new /api/web-chat/sessions
  ├─ new /api/web-chat/sessions/{id}/messages
  ├─ new /api/web-chat/runs
  ├─ new /api/web-chat/runs/{id}/events  (SSE)
  ├─ new /api/web-chat/runs/{id}/stop
  └─ existing AIAgent + SessionDB + tool events
```

Key decision: use Hermes-native `/api/web-chat/*`, not the OpenAI-compatible `/v1/chat/completions`, because the UI needs Hermes-specific events: tool calls, approvals, working directory, model/provider, media attachments, errors, token usage, and interruption state.

## Backend contract

### 1. List sessions

`GET /api/web-chat/sessions?limit=50&cursor=...`

```ts
type WebChatSession = {
  id: string
  title: string | null
  createdAt: string
  updatedAt: string
  workspace: string | null
  model: string | null
  provider: string | null
}
```

Backed by existing Hermes session DB, not a new Nuxt DB.

### 2. Get session messages

`GET /api/web-chat/sessions/{sessionId}`

```ts
type WebChatMessage = {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  parts: WebChatPart[]
  createdAt: string
}

type WebChatPart =
  | { type: 'text'; text: string }
  | { type: 'reasoning'; text: string }
  | { type: 'tool'; toolCallId: string; name: string; status: 'running' | 'completed' | 'error'; input?: unknown; output?: unknown }
  | { type: 'media'; url: string; mediaType: string; name?: string }
  | { type: 'approval'; approvalId: string; title: string; command?: string; status: 'pending' | 'approved' | 'denied' }
```

### 3. Start/send run

`POST /api/web-chat/runs`

```ts
type StartRunRequest = {
  sessionId?: string
  input: string
  workspace?: string
  model?: string
  provider?: string
  enabledToolsets?: string[]
  attachments?: Array<{ name: string; mediaType: string; dataUrl?: string; url?: string }>
}

type StartRunResponse = {
  sessionId: string
  runId: string
}
```

### 4. Stream run events

`GET /api/web-chat/runs/{runId}/events`

Use SSE. Event shape should be small and append-only:

```ts
type WebChatEvent =
  | { type: 'message.created'; message: WebChatMessage }
  | { type: 'message.part.delta'; messageId: string; partIndex: number; text: string }
  | { type: 'tool.started'; messageId: string; part: WebChatPart }
  | { type: 'tool.updated'; messageId: string; toolCallId: string; status: string; output?: unknown }
  | { type: 'approval.requested'; approval: WebChatPart }
  | { type: 'run.completed'; finalMessage?: WebChatMessage; usage?: unknown }
  | { type: 'run.failed'; error: { message: string; code?: string } }
```

### 5. Stop and approvals

- `POST /api/web-chat/runs/{runId}/stop`
- `POST /api/web-chat/approvals/{approvalId}` with `{ decision: 'approve' | 'deny', once?: boolean }`

## Nuxt implementation plan

### Phase 1 — Nuxt shell

Create `web-nuxt/` or replace `web/` after validation.

Dependencies:

- `nuxt`
- `@nuxt/ui`
- `@comark/nuxt`
- `@ai-sdk/vue` only if we adapt to AI SDK transport; otherwise use native `EventSource` composable.
- `date-fns`

Do not copy NuxtHub, Drizzle, GitHub auth, blob upload, or template DB unless needed. Hermes already has persistence and local dashboard auth.

### Phase 2 — dashboard layout

Port template layout into Hermes terms:

- `app.vue`: `UApp`, loading indicator, SEO.
- `layouts/default.vue`: `UDashboardGroup` + sidebar.
- Sidebar items:
  - New chat
  - Recent sessions grouped by date
  - Config
  - Logs
  - Skills/tools
  - Cron
- Keep the session token auth model from current dashboard.

### Phase 3 — chat UX

Use template components directly:

- `UChatMessages` for message list.
- `UChatPrompt` for input.
- `UChatPromptSubmit` for send/stop/retry.
- `UChatReasoning` for Hermes reasoning text.
- `UChatTool` for tool calls.
- Custom `ChatApproval.vue` for approve/deny UI.
- `Comark` for assistant Markdown.

Routes:

- `/` or `/chat`: new chat screen.
- `/chat/[id]`: session chat screen.

### Phase 4 — streaming composable

Create `app/composables/useHermesChat.ts`:

Responsibilities:

- Load existing messages.
- Send prompt via `POST /api/web-chat/runs`.
- Subscribe to `EventSource /api/web-chat/runs/{runId}/events`.
- Convert Hermes events into Nuxt UI message parts.
- Stop current run.
- Retry last user message.
- Handle reconnect/failure states.

Avoid forcing Hermes into Vercel AI SDK format unless it naturally fits. A native composable will be simpler and preserve Hermes-specific semantics.

### Phase 5 — backend FastAPI endpoints

Extend `hermes_cli/web_server.py` or extract to `hermes_cli/web_chat.py` to avoid making `web_server.py` larger.

Recommended extraction:

```text
hermes_cli/web_chat.py
  router = APIRouter(prefix='/api/web-chat')
  list_sessions()
  get_session()
  start_run()
  stream_run_events()
  stop_run()
  respond_approval()
```

Wire router from `web_server.py` and keep existing auth middleware protecting `/api/*`.

Use existing `AIAgent.run_conversation()` first. For richer streaming, expose a small event callback bridge from the agent/tool runner rather than parsing terminal output.

### Phase 6 — build integration

Current FastAPI serves `WEB_DIST`. For Nuxt there are two sane options:

1. **Static SPA mode first:** `nuxt generate`, serve `.output/public` via FastAPI. Best for local dashboard.
2. **Nuxt SSR later:** run Nitro beside FastAPI or proxy through FastAPI. More moving parts; not needed initially.

Recommendation: start with static SPA mode.

Package scripts:

```json
{
  "scripts": {
    "dev": "nuxt dev",
    "build": "nuxt generate",
    "typecheck": "nuxt typecheck"
  }
}
```

Then update release/build script to copy `web-nuxt/.output/public` into `hermes_cli/web_dist`.

## Migration strategy

1. Keep existing React dashboard untouched.
2. Add `web-nuxt/` behind a flag: `HERMES_DASHBOARD_NUXT=1` or `hermes dashboard --nuxt`.
3. Implement only chat first.
4. Reuse existing REST APIs for config/logs/skills later.
5. Once chat is stable, port the rest of the dashboard pages.
6. Remove React/xterm chat only after parity on:
   - session resume
   - interrupt/stop
   - approvals
   - file/media display
   - tool progress
   - copy last response
   - mobile layout

## What to copy from the template

Copy/adapt:

- layout pattern from `app/layouts/default.vue`
- chat page structure from `app/pages/chat/[id].vue`
- message rendering split from `app/components/chat/message/MessageContent.vue`
- grouped sessions logic from `app/composables/useChats.ts`
- Markdown rendering via `ChatComark`

Do not copy/adapt initially:

- NuxtHub DB
- Drizzle schema/migrations
- GitHub OAuth
- Vercel AI provider server code
- weather/chart demo tools
- public/private chat visibility
- votes

## Main risks

- **Streaming fidelity:** current `AIAgent.run_conversation()` is synchronous; web UI needs typed events. Start with final-response streaming via `/v1/runs` only if necessary, but target structured agent events.
- **Approvals:** must not be flattened into text. They need first-class UI events.
- **Security:** preserve `X-Hermes-Session-Token`, Host-header validation, localhost-only CORS, and avoid exposing config/env endpoints unauthenticated.
- **Session correctness:** use existing SessionDB as source of truth; avoid a second chat DB in Nuxt.
- **Scope creep:** do not port all dashboard pages before chat protocol is solid.

## Suggested first milestone

A minimal, shippable Nuxt chat:

- Shows session list.
- Starts a new Hermes run.
- Displays user prompt immediately.
- Streams/updates assistant final response from SSE.
- Supports stop.
- Persists/resumes sessions through existing Hermes session DB.
- Uses Nuxt UI chat components and Comark rendering.

Verification:

- `npm --prefix web-nuxt run typecheck`
- `npm --prefix web-nuxt run build`
- Python tests for new FastAPI endpoints.
- Browser manual test: new chat, long-running tool use, stop, resume session, invalid token returns 401.
