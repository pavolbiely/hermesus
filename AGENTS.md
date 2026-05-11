# AGENTS.md

## Project Overview

This repository is the project-local prototype for a native Nuxt UI chat interface for Hermes Agent. The runtime integration is ACP-native: browser UI talks to same-origin Nuxt/Nitro routes, and Nitro owns the `hermes acp` subprocess through the official Agent Client Protocol TypeScript SDK.

Treat this repository as the source of truth for prototype work. Do not edit `$HOME/.hermes/hermes-agent` directly unless the user explicitly approves it.

## Repository Map

- `web/`: Nuxt 4 app using Nuxt UI, Comark, Nitro server routes, and the ACP TypeScript SDK.
- `web/app`: Nuxt application code, pages, components, composables, types, and assets.
- `web/app/pages/acp/[id].vue`: main ACP-native chat route.
- `web/server/acp/`: ACP bridge, event backlog, transcript/session helpers, and server-owned ACP runtime state.
- `web/server/api/acp/`: ACP protocol-backed Nitro routes for sessions, prompts, cancellation, metadata, permissions, and event streaming.
- `web/server/api/app/`: Hermesum-owned product routes for workspace/settings concerns that ACP does not own.
- `run-local.sh`: local Nuxt dev/preview orchestration.
- `.runtime/`: disposable generated/runtime state. Do not treat it as source code.

## Core Engineering Rules

- Prefer small, clear, maintainable changes over clever or broad rewrites.
- Understand existing flow before changing code, especially ACP bridge state, SSE streaming, session replay, permission handling, and transcript normalization.
- Keep code reusable where reuse is real, but avoid generic abstractions for one-off prototype code.
- Favor focused modules, typed boundaries, explicit validation, and predictable error handling.
- Prefer project-native and framework-native APIs before adding new dependencies.
- Keep `README.md` updated when project structure, setup, development workflow, implemented behavior, or verification commands change.
- Keep `.hermes/agent-map.md` updated when code boundaries, high-token hotspots, first-read files, or verification entrypoints change.
- Keep the active `.hermes/plans/*.md` file updated when completing or materially changing a planned refactor slice; avoid creating overlapping plans for the same work.
- Do not update project docs mechanically after every small edit. Update `AGENTS.md`, `.hermes/agent-map.md`, `README.md`, and active plans only when the change affects future agent navigation, architecture boundaries, setup/workflow, behavior, or verification.
- Do not add new large catch-all files. When a file starts mixing unrelated concerns or grows past a comfortable review size, split it into cohesive modules before adding more behavior.
- Keep the source tree clean: do not commit generated `.nuxt`, `.output`, `node_modules`, runtime copies, logs, or disposable verification artifacts.

## Architecture Boundaries

- `web/server/acp/` owns protocol/runtime behavior: ACP process lifecycle, session load/list/fork/close, prompt/cancel, permission requests, model/mode/config metadata, SSE backlog, replay capture, and transcript normalization inputs.
- `web/server/api/acp/` exposes ACP-shaped HTTP/SSE routes. Do not recreate old `/api/web-chat/*` compatibility contracts.
- `web/server/api/app/` and `web/server/app/` own Hermesum product features that ACP does not own, such as workspace settings and future file/git/voice/update routes.
- `web/app` consumes only same-origin `/api/acp/*` or `/api/app/*` contracts through typed composables.
- Shared request/response shapes should remain aligned between Nitro handlers and TypeScript frontend types.
- Do not wire browser code directly to ACP stdio. Browser ACP interaction must go through Nitro/server routes.

## ACP Backend Rules

- Use the official `@agentclientprotocol/sdk`; inspect installed SDK types/examples before guessing APIs.
- Keep one long-lived ACP subprocess per server process unless a change explicitly requires otherwise.
- Model correctness with explicit ACP/session identities: `sessionId`, prompt `turnId`, ACP message ids, tool ids, request ids, and server event sequences.
- Do not use text equality, timestamps, “last assistant message”, or delayed snapshot patching as primary reconciliation mechanisms.
- Capture `session/load` replay events server-side and return them with the load/transcript response when they can occur before browser SSE subscription.
- Keep SSE events replayable through a bounded per-session backlog so prompt events emitted before browser subscription are not dropped.
- Permission handling must be safe: visible request, validated option id, resolve once, and cancel/deny rather than silently allow when unsupported.
- Treat `hermes acp` stderr diagnostics as logs, not health failures. Health failures are spawn errors, exits, initialization failures, or aborted connections.

## Frontend Rules

- Use Nuxt 4, Vue 3, TypeScript strict mode, Nuxt UI, and Comark idiomatically.
- Prefer existing Nuxt UI chat/dashboard components before creating custom UI primitives.
- Keep chat UI on `UChatMessages`, `UChatMessage`, `UChatTool`, `UChatReasoning`, `UChatShimmer`, `UChatPrompt`, and `UChatPromptSubmit` where practical.
- Keep components typed and simple. Avoid broad `any`, implicit event payloads, and hidden assumptions about backend data.
- Prefer computed state over duplicated reactive state.
- Handle loading, empty, streaming, stopped, failed, permission, and disconnected states explicitly.
- Keep API access behind focused composables such as `useAcpApi` and app-specific composables.
- Do not hardcode backend origins in UI code. Use same-origin `/api/...`.
- Do not rely on stale static output while developing. Use dev mode for normal UI work and production preview for ACP smoke when Nuxt dev routing is suspect.

## Reusability and Extensibility

- Extract reusable frontend behavior into composables only when it is used by multiple views or clearly belongs to a stable API boundary.
- Extract reusable server behavior into small helpers/classes when it reduces duplication in ACP bridge, routes, session metadata, transcript handling, or tests.
- Keep extension points around stable concepts: sessions, prompts, events, permissions, model/mode metadata, workspaces, and app metadata.
- Avoid abstractions based only on current layout or temporary prototype UI structure.
- Prefer explicit option objects for functions likely to grow, but keep simple functions simple.
- Keep frontend TypeScript types close to the API surface they describe.
- When adding new API fields, make defaults/backwards compatibility explicit.

## Development Workflow

Use fast dev mode for normal UI work:

```sh
./run-local.sh --dev
```

This starts the Nuxt dev server on `http://127.0.0.1:3019` by default; override bind host/port with `WEB_DEV_HOST` and `WEB_DEV_PORT`.

For isolated frontend work:

```sh
cd web
pnpm install
pnpm dev
```

For production-style Nitro preview:

```sh
./run-local.sh
```

Important behavior:

- Frontend changes in dev mode should use Nuxt/Vite HMR and should not require `pnpm build`.
- Production preview runs the built Nitro server from `web/.output/server/index.mjs`; rebuild and restart after changes.
- ACP API/browser smoke is often more reliable against production preview than Nuxt dev mode.

## Verification

Prefer the smallest verification command that covers the touched area. Do not claim verification unless it was actually run.

From `web/`:

```sh
node --test tests/*.test.mjs
pnpm typecheck
pnpm build
```

For API/browser smoke, start a fresh preview on a safe unused port:

```sh
cd web
pnpm build
PORT=4046 HOST=127.0.0.1 node .output/server/index.mjs
```

Then check at least:

```sh
curl http://127.0.0.1:4046/api/acp/health
curl -X POST http://127.0.0.1:4046/api/acp/initialize
curl http://127.0.0.1:4046/api/acp/sessions
```

Browser smoke should confirm the app renders beyond the startup loader, sidebar sessions load, a chat can open, a prompt streams, tool/permission states remain safe, and no `/api/web-chat/*` requests are made.

## Change Coordination Checklist

Before finalizing changes, check:

- Did the change touch this repository root and not `$HOME/.hermes/hermes-agent` or another project?
- Are Nitro route payloads, frontend types, and API composables aligned?
- Are SSE event names and payloads compatible with frontend consumers?
- Are prompt cancellation, cleanup, permission resolution, and client disconnects handled?
- Are Nuxt UI components used through their intended APIs before custom markup was added?
- Are generated/runtime artifacts excluded from source changes?
- Was the smallest relevant verification run?
- Are any skipped checks or known pre-existing warnings stated clearly?

## Safety Notes

- Do not modify `$HOME/.hermes/hermes-agent` directly without explicit approval.
- Do not perform global package-manager changes or Homebrew install/uninstall actions without explicit approval.
- Do not add secrets or session tokens to committed files.
- Treat `.runtime/`, copied upstream files, and static/build output as disposable unless explicitly promoted into source.
