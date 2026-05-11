# Hermesum

Hermesum is a native web chat prototype for Hermes Agent: a focused, product-grade interface for running ACP-native agent conversations, choosing workspaces and models, streaming responses, inspecting tool calls, and managing sessions without leaving the browser.

It combines:

- a polished Nuxt chat frontend built for everyday agent work
- a Nitro server runtime that talks to `hermes acp` through the official Agent Client Protocol TypeScript SDK
- ACP session list/load/replay, prompt streaming, cancellation, permissions, and model/mode metadata
- Hermesum-owned app routes for product features that ACP does not own, such as workspace settings

## Preview

<p>
  <img src="docs/assets/agent1.png" alt="Hermesum chat preview" width="49%">
  <img src="docs/assets/agent2.png" alt="Hermesum workspace changes preview" width="49%">
</p>

## Why Hermesum

Hermes Agent is powerful. Hermesum focuses on making that power feel approachable, observable, and controllable in a browser.

The product direction is simple:

- a chat-first workspace for serious agent sessions
- fast streaming with clear prompt status, stop/cancel controls, and deterministic transcript ordering
- visible reasoning, tool activity, plans, permissions, durations, and usage signals where ACP provides them
- workspace context and app-owned metadata for session organization
- practical controls for models, modes, commands, and project switching

## Product Highlights

### ACP-native agent chat

- Same-origin `/api/acp/*` routes backed by a Nitro-owned `hermes acp` subprocess.
- Prompt streaming over SSE with a bounded per-session backlog so early events are replayed instead of dropped.
- Session load replay capture for older CLI-created sessions.
- Persistent normalized transcript projection for fast chat opens, latest-message paging, and explicit rebuild/debug workflows.
- Transcript reconciliation keyed by ACP/session identities, not text/timestamp matching.
- Safe permission-request handling through explicit UI/server resolution.
- Queued follow-up messages and draft persistence for smoother continuation.

### Workspace and session organization

- Workspace selection stored through Hermesum app routes.
- ACP sidebar list with Hermesum-owned title, pin, archive, and workspace grouping metadata.
- ACP-native session actions where available: load, fork/duplicate, close, model/mode/config updates.

### Better inspection and review

- Nuxt UI chat rendering for assistant messages, reasoning, tool activity, and command metadata.
- Comark markdown rendering for assistant and reasoning content.
- Local helper tests for ACP event normalization, sidebar session mapping, queued messages, read receipts, and UI utilities.

## What Exists Today

### Frontend

- Nuxt 4 app in [`web/`](web)
- ACP-native chat route at `/acp/:sessionId`
- new-chat handoff from `/` into ACP session creation
- ACP session sidebar with app-owned metadata actions
- model/mode/config controls from ACP session metadata
- live ACP plan card from `session/update` plan events
- local slash-command autocomplete UI
- workspace selector backed by `/api/app/workspaces`
- read receipts, drafts, queued messages, sound settings, and layout polish

### Server runtime

The server-side runtime is implemented with Nitro routes and the official ACP TypeScript SDK.

It handles:

- `hermes acp` process lifecycle and initialization
- ACP session list/create/load/fork/close
- prompt start, cancellation, and session-scoped SSE events
- server-side replay capture for `session/load` plus stored transcript projection rebuilds
- active prompt correlation so assistant chunks attach to the right user turn
- fast transcript reads, projection invalidation, and manual projection rebuild routes
- permission request publication and resolution
- app-owned ACP session metadata and workspace settings

Hermes Agent remains the actual agent runtime, accessed through ACP.

## Safety Model

Hermesum treats this repository as the source of truth for prototype work.

- Do not edit `$HOME/.hermes/hermes-agent` directly.
- Browser code never talks to ACP stdio directly; it uses same-origin Nitro routes.
- Runtime/build artifacts under `.runtime/`, `.nuxt/`, `.output/`, and `node_modules/` are disposable.
- Global package-manager changes and Hermes runtime updates remain approval-sensitive.

## Quick Start

### Dev mode

For normal UI work:

```bash
./run-local.sh --dev
```

Then open `http://127.0.0.1:3019/`.

This mode:

- starts the Nuxt dev server on `http://127.0.0.1:3019`
- serves same-origin Nitro routes for `/api/acp/*` and `/api/app/*`
- reloads frontend changes through Vite HMR
- cleans up stale local server ports before startup

Useful overrides:

```bash
WEB_DEV_PORT=3020 ./run-local.sh --dev
WEB_DEV_HOST=0.0.0.0 ./run-local.sh --dev
```

### Direct frontend commands

```bash
cd web
pnpm install
pnpm dev
```

### Production-style preview

```bash
./run-local.sh
```

This builds `web/` and starts the Nitro server from `web/.output/server/index.mjs` on `http://127.0.0.1:9119` by default. Override with `PORT=9120 ./run-local.sh`.

## Repo Structure

```text
web/                                        # Nuxt/Nitro app
  app/components/                           # chat, sidebar, workspace, and layout UI
  app/composables/                          # ACP/app API clients and local UI state
  app/pages/acp/[id].vue                    # ACP-native chat route
  app/types/                                # ACP API, ACP transcript, and UI chat types
  app/utils/                                # ACP normalization re-exports, sidebar mapping, drafts, sounds, etc.
  shared/acp/                               # server/browser-safe transcript types and event normalization
  server/acp/                               # ACP SDK bridge, event backlog, transcript projection, and runtime helpers
  server/api/acp/                           # ACP protocol-backed Nitro routes
  server/api/app/                           # Hermesum-owned product routes
  server/app/                               # app metadata/workspace helpers
run-local.sh                                # local Nuxt dev/preview orchestration
.runtime/                                   # disposable generated runtime state
```

## Development Notes

- Use `./run-local.sh --dev` for normal UI work.
- Use production preview for ACP API/browser smoke when Nuxt dev mode behaves differently from the built Nitro server.
- Before agentic coding, check [`.hermes/agent-map.md`](.hermes/agent-map.md) and run `node scripts/report-hotspots.mjs` if broad file targeting is needed.
- Keep `.hermes/agent-map.md`, active `.hermes/plans/*.md`, and this README current when code boundaries, developer workflow, verification commands, or implemented behavior change.
- Use `/api/acp/*` for ACP runtime behavior and `/api/app/*` for Hermesum-owned product concerns.
- Transcript display is projection-first: the chat route reads `/api/acp/sessions/:id/transcript` before background ACP activation, and older history is paged with the transcript endpoint instead of blocking on `session/load` replay.
- Treat workspace, voice, and session-management features as high-trust flows; prefer explicit validation and clear UI feedback.

### Transcript projection debugging

Hermesum stores a rebuildable normalized transcript projection under `.runtime/acp-transcripts/` for fast chat display. These routes affect only the Hermesum projection, not the underlying Hermes Agent session data:

```bash
# Read latest projected messages
curl 'http://127.0.0.1:4046/api/acp/sessions/<sessionId>/transcript?limit=20'

# Read older messages before a returned nextBefore cursor
curl 'http://127.0.0.1:4046/api/acp/sessions/<sessionId>/transcript?limit=20&before=<nextBefore>'

# Delete one local projection
curl -X DELETE 'http://127.0.0.1:4046/api/acp/sessions/<sessionId>/transcript'

# Rebuild one projection from ACP session/load replay
curl -X POST 'http://127.0.0.1:4046/api/acp/sessions/<sessionId>/transcript/rebuild'
```

## Verification

GitHub Actions runs the web checks on every push and pull request via [`.github/workflows/tests.yml`](.github/workflows/tests.yml).

From [`web/`](web):

```bash
node --test tests/*.test.mjs
pnpm typecheck
pnpm build
```

API smoke against a production preview:

```bash
cd web
pnpm build
PORT=4046 HOST=127.0.0.1 node .output/server/index.mjs
curl http://127.0.0.1:4046/api/acp/health
curl -X POST http://127.0.0.1:4046/api/acp/initialize
curl http://127.0.0.1:4046/api/acp/sessions
curl 'http://127.0.0.1:4046/api/acp/sessions/<sessionId>/transcript?limit=20'
```

Browser smoke should confirm the app renders beyond the startup loader, the sidebar lists ACP/CLI sessions, opening a session shows transcript content, sending a prompt streams visibly, cancel/permission paths remain safe, model/mode controls render when exposed by ACP, and workspace selection affects new session cwd.

## Positioning

Hermesum is not trying to replace Hermes Agent internals. It is a prototype for a better operator experience on top of them: ACP-native, more understandable, more inspectable, and closer to something people would actually want to use every day.
