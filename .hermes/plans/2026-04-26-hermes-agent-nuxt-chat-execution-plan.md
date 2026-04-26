# Hermes Agent Nuxt Chat Execution Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a first-class Nuxt UI chat frontend for Hermes Agent without routing user interaction through xterm/PTY.

**Architecture:** Add a native `/api/web-chat/*` FastAPI layer that exposes Hermes sessions, runs, run events, stop, and approvals. Build a Nuxt 4 static SPA using Nuxt UI chat components and serve it through the existing dashboard static-file mechanism. Keep the current React/xterm dashboard available behind the existing flag until parity is proven.

**Tech Stack:** FastAPI, Python pytest, Hermes `AIAgent`, `SessionDB`, Nuxt 4, @nuxt/ui v4, @comark/nuxt, TypeScript, SSE/EventSource.

---

## Grounding from inspected code

- Current Hermes repo: `/Users/pavolbiely/.hermes/hermes-agent`.
- Current dashboard frontend: `web/` React/Vite.
- Current chat page: `web/src/pages/ChatPage.tsx`; embeds `hermes --tui` through `/api/pty`.
- Dashboard backend: `hermes_cli/web_server.py`.
- Existing dashboard auth: ephemeral `X-Hermes-Session-Token` checked by middleware for `/api/*`.
- Existing SPA static serving: `mount_spa()` in `hermes_cli/web_server.py`, using `WEB_DIST` and injecting `window.__HERMES_SESSION_TOKEN__`.
- Existing session store: `hermes_state.py` with `SessionDB` methods:
  - `list_sessions_rich()`
  - `get_session()`
  - `get_messages()`
  - `get_messages_as_conversation()`
  - `create_session()` / `ensure_session()`
  - `reopen_session()`
  - `set_session_title()`
- Existing async run model reference: `gateway/platforms/api_server.py` has `/v1/runs`, SSE events, stop handling. Reuse patterns, not the OpenAI API shape.
- Nuxt template cloned at `.hermes/vendor/nuxt-ui-chat-template`.

---

## Phase 0 — Project-local implementation workspace

### Task 0.1: Keep source work inside `/Users/pavolbiely/Sites/hermesum`

**Objective:** Do not modify `/Users/pavolbiely/.hermes/hermes-agent` during planning/prototyping. Keep all generated source, patches, and Nuxt prototype files under the selected project workspace.

**Files:**
- Project workspace: `/Users/pavolbiely/Sites/hermesum`
- Backend prototype: `.hermes/implementation/hermes-agent-nuxt-chat/backend/`
- Frontend prototype: `.hermes/implementation/hermes-agent-nuxt-chat/web-nuxt/`
- Patch exports for later application to real Hermes: `.hermes/implementation/hermes-agent-nuxt-chat/backend/patches/`

**Steps:**
1. Verify the real Hermes repo remains untouched except for pre-existing user changes:
   ```bash
   git -C /Users/pavolbiely/.hermes/hermes-agent status --short
   ```
2. Work only in:
   ```bash
   /Users/pavolbiely/Sites/hermesum/.hermes/implementation/hermes-agent-nuxt-chat
   ```
3. Export real-repo changes as patch files instead of applying them directly.

**Verification:** `/Users/pavolbiely/.hermes/hermes-agent` must not gain new changes from this work.

---

## Phase 1 — Backend web-chat contract

### Task 1.1: Add contract models

**Objective:** Create explicit Pydantic models for the Nuxt chat API.

**Files:**
- Create: `hermes_cli/web_chat.py`
- Test: `tests/hermes_cli/test_web_chat.py`

**Implementation sketch:**

```python
from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/web-chat", tags=["web-chat"])

class WebChatPart(BaseModel):
    type: Literal["text", "reasoning", "tool", "media", "approval"]
    text: Optional[str] = None
    name: Optional[str] = None
    status: Optional[str] = None
    input: Optional[Any] = None
    output: Optional[Any] = None
    url: Optional[str] = None
    mediaType: Optional[str] = None
    approvalId: Optional[str] = None

class WebChatMessage(BaseModel):
    id: str
    role: Literal["user", "assistant", "system", "tool"]
    parts: List[WebChatPart]
    createdAt: str

class StartRunRequest(BaseModel):
    sessionId: Optional[str] = None
    input: str = Field(min_length=1, max_length=65536)
    workspace: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    enabledToolsets: Optional[List[str]] = None

class StartRunResponse(BaseModel):
    sessionId: str
    runId: str
```

**Testing:**
- Pydantic validation rejects empty input.
- Long input is bounded.

---

### Task 1.2: Add session list endpoint

**Objective:** Expose recent Hermes sessions for sidebar navigation.

**Files:**
- Modify: `hermes_cli/web_chat.py`
- Test: `tests/hermes_cli/test_web_chat.py`

**Endpoint:**

```http
GET /api/web-chat/sessions?limit=50&cursor=...
```

**Implementation notes:**
- Instantiate `SessionDB()` from `hermes_state.py`.
- Prefer `list_sessions_rich(limit=..., include_hidden=False)` if it already supports needed shape.
- Return ISO timestamps from epoch seconds.
- Do not expose system prompt or full raw model config in list endpoint.

**Response shape:**

```ts
type WebChatSession = {
  id: string
  title: string | null
  createdAt: string
  updatedAt: string
  model: string | null
  source: string | null
}
```

**Tests:**
- Creates a temporary `SessionDB` with two sessions.
- Endpoint returns newest first.
- Endpoint caps `limit` to a safe max, e.g. 100.

---

### Task 1.3: Add session detail endpoint

**Objective:** Load one conversation into Nuxt UI message format.

**Files:**
- Modify: `hermes_cli/web_chat.py`
- Test: `tests/hermes_cli/test_web_chat.py`

**Endpoint:**

```http
GET /api/web-chat/sessions/{session_id}
```

**Mapping rules:**
- `messages.content` → `{ type: 'text', text }`
- `messages.reasoning` / `reasoning_content` → `{ type: 'reasoning', text }`
- tool call metadata, if present, → `{ type: 'tool', name, status, input, output }`
- preserve order by `timestamp`.

**Tests:**
- Unknown session returns 404.
- User/assistant messages map to `WebChatMessage`.
- Reasoning column maps to `reasoning` part when present.

---

### Task 1.4: Add run manager

**Objective:** Track active web chat runs in memory so SSE, stop, and status can coordinate.

**Files:**
- Modify: `hermes_cli/web_chat.py`
- Test: `tests/hermes_cli/test_web_chat.py`

**Implementation sketch:**

```python
@dataclass
class WebRun:
    id: str
    session_id: str
    queue: queue.Queue[dict]
    done: threading.Event = field(default_factory=threading.Event)
    agent: Any = None
    error: Optional[str] = None

_runs: dict[str, WebRun] = {}
_runs_lock = threading.Lock()
```

**Rules:**
- Remove completed runs after SSE finishes or after short TTL cleanup.
- Never share queues between sessions.
- Store active agent reference for stop.

**Tests:**
- Starting a run stores it.
- Completion marks it done.
- Failed run emits `run.failed`.

---

### Task 1.5: Add start run endpoint

**Objective:** Start Hermes `AIAgent.run_conversation()` in a background thread and return `{ sessionId, runId }` immediately.

**Files:**
- Modify: `hermes_cli/web_chat.py`
- Test: `tests/hermes_cli/test_web_chat.py`

**Endpoint:**

```http
POST /api/web-chat/runs
```

**Implementation notes:**
- Create or reuse `sessionId`.
- Use `AIAgent(session_id=session_id, platform='web', ...)`.
- Pass `workspace` into agent/workdir only after validating path policy; do not blindly trust arbitrary paths.
- First implementation can emit:
  - `message.created` for user message
  - `message.created` placeholder assistant
  - `message.part.delta` once with final response
  - `run.completed`
- Later implementation can add token/tool deltas.

**Tests:**
- Mock `AIAgent` so no real model call happens.
- Endpoint returns 202/200 with run ID.
- Queue receives final events.
- Empty input returns 422.

---

### Task 1.6: Add SSE event endpoint

**Objective:** Stream web run events to Nuxt.

**Files:**
- Modify: `hermes_cli/web_chat.py`
- Test: `tests/hermes_cli/test_web_chat.py`

**Endpoint:**

```http
GET /api/web-chat/runs/{run_id}/events
```

**SSE format:**

```python
def sse(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
```

**Tests:**
- Unknown run returns 404.
- Completed run streams `run.completed`.
- Error run streams `run.failed`.

---

### Task 1.7: Add stop endpoint

**Objective:** Let `UChatPromptSubmit` stop a running agent.

**Files:**
- Modify: `hermes_cli/web_chat.py`
- Test: `tests/hermes_cli/test_web_chat.py`

**Endpoint:**

```http
POST /api/web-chat/runs/{run_id}/stop
```

**Implementation notes:**
- If `run.agent` has `interrupt()`, call it.
- Emit `run.stopped` or `run.failed` with a clear message.
- Return idempotently if already done.

**Tests:**
- Stop calls mocked `agent.interrupt()`.
- Stop on unknown run returns 404.
- Stop on completed run is safe.

---

### Task 1.8: Wire router into existing dashboard server

**Objective:** Mount `/api/web-chat/*` before SPA catch-all and keep existing token middleware.

**Files:**
- Modify: `hermes_cli/web_server.py`

**Implementation:**

```python
from hermes_cli.web_chat import router as web_chat_router

app.include_router(web_chat_router)
```

Place before `mount_spa(app)` is called. Existing middleware already protects `/api/*` except public allowlist, so web-chat endpoints remain authenticated.

**Tests:**
- Existing `tests/hermes_cli/test_web_server.py` still pass.
- New test confirms unauthenticated `/api/web-chat/sessions` returns 401 through `web_server.app`.

---

## Phase 2 — Nuxt frontend skeleton

### Task 2.1: Create `web-nuxt/`

**Objective:** Add Nuxt app without disrupting existing React dashboard.

**Files:**
- Create: `web-nuxt/package.json`
- Create: `web-nuxt/nuxt.config.ts`
- Create: `web-nuxt/app/app.vue`
- Create: `web-nuxt/app/assets/css/main.css`
- Create: `web-nuxt/tsconfig.json`

**Dependencies:**

```json
{
  "dependencies": {
    "@comark/nuxt": "^0.2.1",
    "@iconify-json/lucide": "^1.2.102",
    "@nuxt/ui": "^4.6.1",
    "date-fns": "^4.1.0",
    "nuxt": "^4.4.2",
    "tailwindcss": "^4.2.2"
  },
  "devDependencies": {
    "typescript": "^6.0.2",
    "vue-tsc": "^3.2.6"
  }
}
```

**Nuxt config:**

```ts
export default defineNuxtConfig({
  modules: ['@nuxt/ui', '@comark/nuxt'],
  css: ['~/assets/css/main.css'],
  ssr: false,
  compatibilityDate: '2024-07-11'
})
```

**Verification:**

```bash
npm --prefix web-nuxt install
npm --prefix web-nuxt run typecheck
npm --prefix web-nuxt run build
```

---

### Task 2.2: Add authenticated API helper

**Objective:** Centralize dashboard token header use.

**Files:**
- Create: `web-nuxt/app/types/hermes.d.ts`
- Create: `web-nuxt/app/utils/api.ts`

**Implementation sketch:**

```ts
declare global {
  interface Window {
    __HERMES_SESSION_TOKEN__?: string
  }
}

export function hermesHeaders(): HeadersInit {
  const token = globalThis.window?.__HERMES_SESSION_TOKEN__
  return token ? { 'X-Hermes-Session-Token': token } : {}
}

export async function hermesFetch<T>(url: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      ...hermesHeaders(),
      ...(options.headers || {})
    }
  })
  if (!res.ok) throw new Error(await res.text())
  return await res.json() as T
}
```

**Tests:** typecheck only initially.

---

### Task 2.3: Port dashboard layout

**Objective:** Use Nuxt UI dashboard layout from template, adapted to Hermes.

**Files:**
- Create: `web-nuxt/app/layouts/default.vue`
- Create: `web-nuxt/app/composables/useSessions.ts`
- Create: `web-nuxt/app/composables/useGroupedSessions.ts`

**Components:**
- `UDashboardGroup`
- `UDashboardSidebar`
- `UNavigationMenu`
- `UDashboardSearch`
- `UButton`

**Rules:**
- Label app as `Hermes`.
- Keep copy in English.
- Use semantic Nuxt UI colors (`text-muted`, `bg-default`, etc.).

**Verification:** `npm --prefix web-nuxt run typecheck`.

---

### Task 2.4: New chat page

**Objective:** Provide initial prompt screen.

**Files:**
- Create: `web-nuxt/app/pages/index.vue`
- Create: `web-nuxt/app/pages/chat/index.vue` if redirect preferred

**Behavior:**
- Prompt box centered.
- On submit, call `POST /api/web-chat/runs`.
- Navigate to `/chat/{sessionId}`.
- Subscribe to current run after navigation via query param `?run={runId}` or local state.

**Verification:** typecheck + manual browser test.

---

### Task 2.5: Chat session page

**Objective:** Render session history and stream active run events.

**Files:**
- Create: `web-nuxt/app/pages/chat/[id].vue`
- Create: `web-nuxt/app/components/chat/MessageContent.vue`
- Create: `web-nuxt/app/components/chat/ApprovalCard.vue`
- Create: `web-nuxt/app/components/chat/ToolPart.vue`

**Use:**
- `UChatMessages`
- `UChatPrompt`
- `UChatPromptSubmit`
- `UChatReasoning`
- `UChatTool`
- `Comark`

**Verification:** typecheck + manual browser test.

---

### Task 2.6: Streaming composable

**Objective:** Keep pages simple by isolating SSE and message mutation logic.

**Files:**
- Create: `web-nuxt/app/composables/useHermesChat.ts`

**API:**

```ts
export function useHermesChat(sessionId: Ref<string>) {
  const messages = ref<WebChatMessage[]>([])
  const status = ref<'ready' | 'submitted' | 'streaming' | 'error'>('ready')
  const error = ref<Error | null>(null)

  async function load(): Promise<void> {}
  async function send(input: string): Promise<void> {}
  async function stop(): Promise<void> {}
  function attachRun(runId: string): void {}

  return { messages, status, error, load, send, stop, attachRun }
}
```

**Event handling:**
- `message.created`: append if not already present.
- `message.part.delta`: append text to target part.
- `tool.started` / `tool.updated`: mutate matching part.
- `run.completed`: set status `ready`, close EventSource.
- `run.failed`: set status `error`, show toast.

**Verification:** add unit tests if frontend test stack exists; otherwise typecheck and manual test.

---

## Phase 3 — Build/release integration

### Task 3.1: Add Nuxt build option without replacing React build

**Objective:** Support choosing Nuxt dist via env var first.

**Files:**
- Modify: packaging/build scripts only after locating existing release script.
- Existing server already supports `HERMES_WEB_DIST`.

**Low-risk first path:**

```bash
npm --prefix web-nuxt run build
HERMES_WEB_DIST=/Users/pavolbiely/.hermes/hermes-agent/web-nuxt/.output/public hermes dashboard
```

**Verification:** dashboard serves Nuxt static assets and token injection works.

---

### Task 3.2: Add CLI flag later

**Objective:** Add `hermes dashboard --nuxt` only after Nuxt build works via env var.

**Files:**
- Locate dashboard command in `hermes_cli/main.py`.
- Modify parser and start-server call.

**Behavior:**
- `--nuxt` sets `WEB_DIST` or chooses Nuxt build dir.
- Does not remove `--tui` / embedded PTY mode.

---

## Phase 4 — Parity checklist

Ship only after these pass:

- New chat starts a run.
- Existing session opens from sidebar.
- Stop interrupts a running agent.
- Errors surface as `UToast`.
- Reasoning parts display in `UChatReasoning`.
- Tool starts/completions display in `UChatTool`.
- Approval requests are interactive and cannot be missed.
- Session list updates after first user message/final response.
- Invalid/missing token returns 401.
- Host-header and localhost protections remain intact.
- Mobile layout works without xterm-specific hacks.

---

## Commands for implementation verification

Backend:

```bash
cd /Users/pavolbiely/.hermes/hermes-agent
source .venv/bin/activate || source venv/bin/activate
pytest tests/hermes_cli/test_web_chat.py tests/hermes_cli/test_web_server.py -q
```

Frontend:

```bash
cd /Users/pavolbiely/.hermes/hermes-agent
npm --prefix web-nuxt run typecheck
npm --prefix web-nuxt run build
```

Manual:

```bash
cd /Users/pavolbiely/.hermes/hermes-agent
HERMES_WEB_DIST="$PWD/web-nuxt/.output/public" python -m hermes_cli.main dashboard --no-open
```

Then open the printed localhost URL and verify chat flow.

---

## Implementation order recommendation

1. Backend read-only endpoints: sessions + session detail.
2. Nuxt shell + sidebar + read-only session display.
3. Backend run start + SSE final response only.
4. Nuxt prompt send + stop.
5. Add richer events: tool status, reasoning, approvals.
6. Build integration / CLI flag.

This keeps each step testable and avoids committing to a fragile streaming abstraction too early.
