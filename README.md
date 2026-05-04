# Hermesum

Hermesum is a native web chat prototype for Hermes Agent: a focused, product-grade interface for running agent conversations, choosing workspaces and models, streaming responses, inspecting tool calls, and reviewing code changes without leaving the chat.

It combines:

- a polished Nuxt chat frontend built for everyday agent work
- a FastAPI web-chat API that mirrors real Hermes runtime behavior
- a disposable local Hermes runtime copy for safe iteration
- workspace-aware files, attachments, and code-change history

## Preview

<p>
  <img src="docs/assets/agent1.png" alt="Hermesum chat preview" width="49%">
  <img src="docs/assets/agent2.png" alt="Hermesum workspace changes preview" width="49%">
</p>

## Why Hermesum

Hermes Agent is powerful. Hermesum focuses on making that power feel approachable, observable, and controllable in a browser.

The product direction is simple:

- a chat-first workspace for serious agent sessions
- fast streaming with clear run status, stop, continue, and steer controls
- visible reasoning, tool activity, durations, and usage signals
- workspace context with file previews and code-change history
- practical controls for models, profiles, and project switching

If someone lands on this repository, they should immediately understand that Hermesum is a serious prototype for a native Hermes chat experience, not a throwaway demo.

## Product Highlights

### Agent chat that feels alive

- Streaming responses over SSE with clear run status and stop controls.
- Queued follow-up messages for smoother continuation and steering.
- Regenerate response support from the original user prompt.
- In-flight activity indicators for a clearer sense of what the agent is doing.
- Message editing, copying, attachments, and continuation flows designed around real chat usage.

### Workspace-aware coding context

- Workspace and project switching built into the conversation flow.
- Code-change history captured from git so users can review what changed during a session.
- Workspace snapshots and change surfaces that make file modifications visible from chat.
- Lightweight commit-message generation from the current chat and Git diff using project commit-message rules, shown in a small modal with an explicit copy action.
- Local file previews for referenced workspace files, with safe text preview limits.

### Better inspection and review

- Detailed tool-call overviews instead of raw opaque execution blocks.
- Duration tracking for reasoning and tool parts.
- Usage metrics and context-window visibility for model-aware prompting.
- Clipboard file paste support for quickly attaching screenshots and local files.

### Model and profile controls

- Provider, model, reasoning-effort, context-window, and auto-compression metadata surfaced in the UI.
- Profile switching through the web-chat API.

## What Exists Today

### Frontend

- Nuxt web chat UI in [`web/`](web)
- SSE run streaming with explicit stop handling
- queued messages, steering, and regenerate flows
- model, reasoning-effort, context-usage, profile, and workspace controls
- workspace/session management, pinning, unread states, and project switching
- code-change history, workspace snapshots, and change review surfaces
- attachment upload, clipboard file paste, inline previews, and local file preview modals
- reasoning, tool-call, duration, usage, and activity detail views
- authenticated same-origin API access

### Backend

The backend makes the chat feel responsive and dependable instead of exposing Hermes as a loose collection of commands.

It handles:

- conversation history, pinned sessions, unread state, and duplicated sessions
- live agent runs with streaming updates, stop, continue, steer, and regenerate controls
- command execution, profile switching, model capabilities, and workspace selection
- attachments, pasted files, and safe local file previews
- code-change tracking and commit-message generation from the selected workspace
- update checks for the Hermes runtime and the web app shell

The important user benefit is predictability: a run can be watched as it happens, interrupted when needed, continued with more context, inspected afterward, and tied back to the workspace files it changed.

Git integration is intentionally lightweight. It helps users review what changed during a session and generate a commit message from the current chat plus the selected workspace diff. The generated message opens in a small modal with an explicit `Copy` action, and the hidden generation prompt is not added to the visible chat history.

Attachments uploaded from the UI are stored under `.hermes/attachments/` in the selected project and ignored by git in this prototype. Images render inline, supported files open through authenticated previews, and deleted files remain visible in history as unavailable placeholders.

Local file previews are resolved against the selected workspace or its git root, limited to safe text preview sizes, and include language/media metadata for easier code reading in the UI.

## Safety Model

Hermesum treats this repository as the source of truth for prototype work.

- Do not edit `$HOME/.hermes/hermes-agent` directly.
- Runtime integration happens through the disposable `.runtime/hermes-agent` copy created by [`run-local.sh`](run-local.sh).
- The upstream Hermes checkout is copied from, not mutated as part of normal development.

This keeps the prototype portable and easier to upstream into Hermes Agent later.

## Quick Start

### Full dev mode

For normal frontend + backend work:

```bash
./run-local.sh --dev
```

Then open `http://127.0.0.1:3019/`.

This mode:

- starts the Hermes backend/dashboard runtime on `http://127.0.0.1:9119`
- starts the frontend dev server on `http://127.0.0.1:3019`
- proxies `/api/...` requests to Hermes
- shares an ephemeral dev session token for authenticated API and SSE calls
- reloads frontend changes through Vite HMR
- restarts the backend when watched Python files change
- cleans up stale local server ports before startup

Useful overrides:

```bash
PORT=9120 WEB_DEV_PORT=3020 ./run-local.sh --dev
WEB_DEV_HOST=0.0.0.0 ./run-local.sh --dev
```

### Frontend-only mode

For isolated UI work:

```bash
cd web
pnpm install
pnpm dev
```

### Hermes-served static preview

For production-style preview through the disposable Hermes runtime:

```bash
./run-local.sh
```

### Runtime sync only

To refresh the disposable Hermes runtime copy without starting the app:

```bash
./run-local.sh --sync-runtime
```

## Repo Structure

```text
backend/
  hermes_cli/web_chat.py                    # FastAPI web-chat entrypoint
  hermes_cli/web_chat_modules/              # modular backend domains
  tests/hermes_cli/test_web_chat*.py        # split pytest coverage by domain
web/                                        # Nuxt UI prototype
  app/components/                           # chat, sidebar, tool, preview, and layout UI
  app/composables/                          # API, active runs, composer, and workspace state
  app/utils/                                # message, clipboard, file preview, and tool helpers
run-local.sh                                # local runtime orchestration
.runtime/                                   # disposable generated runtime state
```

Key frontend areas include chat rendering, queued-message flows, attachments, file previews, tool-call details, code-change history, update controls, and workspace/session UX. Key backend areas include routes, Pydantic models, run lifecycle, SSE streaming, queue-backed prompts, attachments, workspaces, capabilities, updates, file previews, and git-change persistence.

## Development Notes

- Frontend development should normally use `./run-local.sh --dev`, not repeated static builds.
- Before agentic coding, check [`.hermes/agent-map.md`](.hermes/agent-map.md) and run `node scripts/report-hotspots.mjs` to target the smallest relevant files instead of broad repository scans.
- Keep `.hermes/agent-map.md`, active `.hermes/plans/*.md`, and this README current when code boundaries, developer workflow, verification commands, or implemented behavior change; do not update docs mechanically for tiny local-only edits.
- Keep large UI and backend orchestration files thin: move pure helpers to `web/app/utils`, reusable UI state to `web/app/composables`, and backend domain logic to `backend/hermes_cli/web_chat_modules`.
- Python restarts in watch/dev mode can interrupt in-flight SSE streams.
- Shared request/response shapes should stay aligned between backend Pydantic models and frontend TypeScript types.
- When backend payloads change, update backend models, API behavior, frontend types, frontend composables, and tests together.
- Treat workspace, file-preview, git-history, and update features as high-trust flows; prefer explicit validation and clear UI feedback.

## Verification

Frontend verification from [`web/`](web):

```bash
pnpm typecheck
pnpm build
```

Backend verification:

```bash
python3 -m py_compile backend/hermes_cli/web_chat.py backend/hermes_cli/web_chat_modules/*.py backend/tests/hermes_cli/test_web_chat*.py backend/tests/hermes_cli/conftest.py backend/tests/hermes_cli/web_chat_test_helpers.py
```

Backend pytest should run against the disposable runtime mirror after copying the canonical backend/test files into `.runtime/hermes-agent`; target `backend/tests/hermes_cli/test_web_chat*.py` rather than unrelated upstream runtime tests.

## Positioning

Hermesum is not trying to replace Hermes Agent internals. It is a prototype for a better operator experience on top of them: more understandable, more inspectable, clearer around code changes, and much closer to something people would actually want to use every day.
