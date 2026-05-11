# AGENTS.md

## Project Overview

Hermesum is a Nuxt/Nitro web chat interface for Hermes Agent. The integration is ACP-native: the browser talks to same-origin Nitro routes, Nitro owns a long-lived `hermes acp` subprocess through the official Agent Client Protocol TypeScript SDK, and Hermes Agent remains the actual agent runtime.

Treat this repository as the source of truth for Hermesum work. Do not edit `$HOME/.hermes/hermes-agent` directly unless the user explicitly approves it.

## Repository Map

- `web/`: Nuxt 4 app using Nuxt UI, Comark, Nitro server routes, and `@agentclientprotocol/sdk`.
- `web/app/pages/index.vue`: new-chat entry point and initial ACP session creation.
- `web/app/pages/acp/[id].vue`: main ACP-native chat route.
- `web/app/layouts/default.vue`: app shell, sidebar, workspace/profile controls, settings, and navigation.
- `web/app/components/`: chat, prompt, sidebar, workspace, read-aloud, and utility UI components.
- `web/app/composables/`: typed ACP/app API clients and local browser UI state.
- `web/app/types/`: frontend/API contract types for ACP and UI chat state.
- `web/app/utils/`: ACP normalization re-exports, sidebar mapping, queued messages, drafts, sounds, highlighting, and UI helpers.
- `web/shared/acp/`: browser/server-safe ACP event and transcript normalization helpers.
- `web/server/acp/`: ACP bridge, event backlog, replay capture, permission handling, prompt metadata, and runtime helpers.
- `web/server/api/acp/`: ACP protocol-backed Nitro routes for health, initialize, sessions, prompts, cancellation, metadata, permissions, config, and event streaming.
- `web/server/app/` and `web/server/api/app/`: Hermesum-owned product features that ACP does not own, including workspaces, profile listing, session metadata, and read-aloud speech.
- `web/tests/`: `node:test` coverage for shared helpers, transcript/event normalization, sidebar mapping, workspaces, queued messages, read-aloud, and related utilities.
- `web/nuxt.config.ts`: runtime config for ACP command/args/cwd; defaults to `hermes --profile hermesum acp`.
- `run-local.sh`: local Nuxt dev/preview orchestration.
- `.hermes/agent-map.md`: first-read navigation map for future agents.
- `.runtime/`: disposable generated runtime/cache state. Do not treat it as source code.

## Core Engineering Rules

- Prefer small, clear, maintainable changes over clever or broad rewrites.
- Understand existing flow before changing code, especially ACP bridge state, SSE streaming, session replay, permission handling, and prompt correlation.
- Keep code reusable where reuse is real, but avoid generic abstractions for one-off prototype code.
- Favor focused modules, typed boundaries, explicit validation, and predictable error handling.
- Prefer project-native and framework-native APIs before adding dependencies.
- Do not add new large catch-all files. When a file starts mixing unrelated concerns or grows past a comfortable review size, split it into cohesive modules before adding more behavior.
- Keep the source tree clean: do not commit generated `.nuxt`, `.output`, `node_modules`, runtime copies, logs, or disposable verification artifacts.
- Keep `README.md`, `AGENTS.md`, `.hermes/agent-map.md`, and active `.hermes/plans/*.md` current when behavior, architecture boundaries, setup/workflow, or verification guidance changes. Do not update docs mechanically for tiny local-only edits.

## Architecture Boundaries

- `web/server/acp/` owns protocol/runtime behavior: ACP process lifecycle, session list/create/load/fork/close, prompt/cancel, permission requests, model/mode/config metadata, SSE backlog, replay capture, and prompt metadata supplements.
- `web/server/api/acp/` exposes ACP-backed HTTP/SSE routes. Do not recreate old `/api/web-chat/*` compatibility contracts.
- `web/server/api/app/` and `web/server/app/` own Hermesum product features that ACP does not own: workspaces, profile list, app-owned ACP session metadata, read-aloud speech, and future app-specific features.
- `web/app` consumes only same-origin `/api/acp/*` or `/api/app/*` contracts through typed composables.
- `web/shared/acp/` is the place for normalization code that must be safe on both server and browser.
- Shared request/response shapes must remain aligned between Nitro handlers, frontend composables, and TypeScript UI types.
- Do not wire browser code directly to ACP stdio. Browser ACP interaction must go through Nitro/server routes.

## ACP Runtime Model

- Use the official `@agentclientprotocol/sdk`; inspect installed SDK types/examples before guessing APIs.
- Keep one long-lived ACP subprocess per server process unless a change explicitly requires otherwise.
- Default ACP command is `hermes --profile hermesum acp`. Override with `HERMESUM_PROFILE`, `HERMESUM_ACP_ARGS`, `HERMESUM_ACP_COMMAND`, or `HERMESUM_ACP_CWD` only when intentionally testing another runtime.
- Model correctness with explicit ACP/session identities: `sessionId`, prompt `turnId`, ACP message ids, tool ids, permission request ids, and server event sequences.
- Do not use text equality, timestamps, “last assistant message”, or delayed snapshot patching as primary reconciliation mechanisms.
- Capture `session/load` replay events server-side when they can occur before browser SSE subscription.
- Keep SSE events replayable through a bounded per-session backlog so prompt events emitted before browser subscription are not dropped.
- Transcript display is replay-first: load ACP session replay, then continue from the bounded SSE backlog/live stream.
- Permission handling must be safe: visible request, validated option id, resolve once, and cancel/deny rather than silently allow when unsupported.
- Treat `hermes acp` stderr diagnostics as logs, not health failures. Health failures are spawn errors, exits, initialization failures, aborted connections, or routes that hang because initialization never completed.

## Frontend Rules

- Use Nuxt 4, Vue 3, TypeScript strict mode, Nuxt UI, and Comark idiomatically.
- Prefer existing Nuxt UI chat/dashboard components before creating custom UI primitives.
- Keep chat UI on `UChatMessages`, `UChatMessage`, `UChatTool`, `UChatReasoning`, `UChatShimmer`, `UChatPrompt`, and `UChatPromptSubmit` where practical.
- Keep components typed and simple. Avoid broad `any`, implicit event payloads, and hidden assumptions about backend data.
- Prefer computed state over duplicated reactive state.
- Handle loading, empty, streaming, stopped, failed, permission, queued, and disconnected states explicitly.
- Keep API access behind focused composables such as `useAcpApi` and app-specific composables.
- Do not hardcode backend origins in UI code. Use same-origin `/api/...`.
- Do not rely on stale static output while developing. Use dev mode for normal UI work and production preview for ACP smoke when Nuxt dev routing is suspect.
- When removing UI that used i18n/labels/state, also remove unused keys/state and search for removed labels before finalizing.

## Reusability and Extensibility

- Extract reusable frontend behavior into composables only when it is used by multiple views or clearly belongs to a stable API boundary.
- Extract reusable server behavior into small helpers/classes when it reduces duplication in ACP bridge, routes, session metadata, transcript handling, or tests.
- Keep extension points around stable concepts: sessions, prompts, events, permissions, model/mode metadata, workspaces, profiles, read-aloud, and app metadata.
- Avoid abstractions based only on current layout or temporary prototype UI structure.
- Prefer explicit option objects for functions likely to grow, but keep simple functions simple.
- Keep frontend TypeScript types close to the API surface they describe.
- When adding new API fields, make defaults/backwards compatibility explicit.

## Development Workflow

Use fast dev mode for normal UI work:

```sh
./run-local.sh --dev
```

This starts the Nuxt dev server on `http://127.0.0.1:3019` by default, serves Nitro routes same-origin, and starts ACP with the `hermesum` profile by default.

Useful overrides:

```sh
WEB_DEV_PORT=3020 ./run-local.sh --dev
WEB_DEV_HOST=0.0.0.0 ./run-local.sh --dev
HERMESUM_PROFILE=coder ./run-local.sh --dev
HERMESUM_ACP_ARGS="--profile coder acp" ./run-local.sh --dev
HERMESUM_ACP_CWD=/path/to/workspace ./run-local.sh --dev
```

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
- Runtime config changes in `nuxt.config.ts` or ACP env vars require a dev server restart.
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
curl http://127.0.0.1:4046/api/acp/sessions/<sessionId>
```

Browser smoke should confirm the app renders beyond the startup loader, sidebar sessions load, a chat opens from ACP replay, a prompt streams, cancellation works, tool/reasoning/permission states remain safe, model/mode/config controls render when ACP exposes them, workspace selection affects new session cwd, and no `/api/web-chat/*` requests are made.

Known note: `pnpm typecheck` can exit `0` while printing the Vue/Volar `vue-router/volar/sfc-route-blocks` package export warning. Treat it as a warning when exit code is `0`, not as a touched-code failure.

## ACP Startup Debugging

If the UI hangs on startup, `/api/acp/sessions` times out, or the browser reports module import failures after a bad reload, check ACP health first:

```sh
curl http://127.0.0.1:3019/api/acp/health
```

Expected defaults:

```json
{
  "command": "hermes",
  "args": ["--profile", "hermesum", "acp"],
  "cwd": "/Users/pavolbiely/Sites/hermesum"
}
```

Debug checklist:

- If the profile is not `hermesum`, restart with the expected env or unset stale overrides.
- If unrelated MCP servers are retrying during startup, verify the profile and cwd before changing app code.
- If `initialized` is false and routes hang, inspect `stderr`, process exit state, and runtime env.
- Restart dev server after changing `nuxt.config.ts`, `HERMESUM_PROFILE`, `HERMESUM_ACP_ARGS`, `HERMESUM_ACP_COMMAND`, or `HERMESUM_ACP_CWD`.

## Change Coordination Checklist

Before finalizing changes, check:

- Did the change touch this repository root and not `$HOME/.hermes/hermes-agent` or another project?
- Are Nitro route payloads, frontend types, and API composables aligned?
- Are SSE event names and payloads compatible with frontend consumers?
- Are prompt cancellation, cleanup, permission resolution, and client disconnects handled?
- Are replay capture and active prompt correlation still keyed by ids rather than text/timestamps?
- Are Nuxt UI components used through their intended APIs before custom markup was added?
- Are generated/runtime artifacts excluded from source changes?
- Were docs updated only where the change affects future navigation, architecture, workflow, behavior, or verification?
- Was the smallest relevant verification run?
- Are any skipped checks or known pre-existing warnings stated clearly?

## Safety Notes

- Do not modify `$HOME/.hermes/hermes-agent` directly without explicit approval.
- Do not perform global package-manager changes or Homebrew install/uninstall actions without explicit approval.
- Do not add secrets or session tokens to committed files.
- Treat `.runtime/`, copied upstream files, `.nuxt/`, `.output/`, `node_modules/`, and static/build output as disposable unless explicitly promoted into source.
