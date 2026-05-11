# Hermesum Agent Map

Use this before broad repository search.

## Canonical source

- `web/app/pages/index.vue`: new-chat entry point and initial ACP session creation.
- `web/app/pages/acp/[id].vue`: main ACP-native chat route and composer orchestration.
- `web/app/layouts/default.vue`: app shell, sidebar loading, workspace state, and session navigation.
- `web/app/components/SidebarSessionGroups.vue`: session list rendering and ACP sidebar actions.
- `web/app/components/ChatSlashCommandMenu.vue`: local slash-command autocomplete UI.
- `web/app/composables/useAcpApi.ts`: typed frontend client for `/api/acp/*` routes.
- `web/app/composables/useAcpTranscript.ts`: browser transcript state from ACP replay/live events.
- `web/app/composables/useAppWorkspacesApi.ts`: typed frontend client for Hermesum-owned workspace routes.
- `web/app/types/acp-api.ts`, `web/app/types/acp-chat.ts`, `web/app/types/chat.ts`: API/protocol/UI contract types.
- `web/app/utils/acpBridgeEventNormalization.ts`, `web/app/utils/acpEventNormalization.ts`, and `web/app/utils/acpPlanNormalization.ts`: ACP bridge events to chat transcript/plan state.
- `web/app/utils/acpSidebarSessions.ts`: ACP session/list to sidebar summary mapping.
- `web/server/acp/bridge.ts`: ACP SDK subprocess bridge, active prompt correlation, and client handler.
- `web/server/acp/events.ts`: session-scoped ACP SSE publish/subscribe backlog.
- `web/server/app/acpSessionMetadata.ts`: Hermesum-owned ACP sidebar metadata store.
- `web/server/app/workspaces.ts`: Hermesum-owned workspace settings store and validation.
- `web/server/api/acp/`: ACP protocol-backed Nitro routes.
- `web/server/api/app/`: Hermesum product routes for non-ACP app concerns.
- `.github/workflows/tests.yml`: CI for Node tests, Nuxt typecheck, and Nuxt build.
- `.runtime/`: disposable runtime mirror; do not edit as source.

## High-token hotspots

- ACP chat page: `web/app/pages/acp/[id].vue`.
- Layout/sidebar: `web/app/layouts/default.vue`, `SidebarSessionGroups.vue`.
- ACP bridge/transcript state: `web/server/acp/bridge.ts`, `useAcpTranscript.ts`, `acpBridgeEventNormalization.ts`, `acpEventNormalization.ts`.
- App-owned session metadata/workspaces: `web/server/app/acpSessionMetadata.ts`, `web/server/app/workspaces.ts`.
- Run/local orchestration: `run-local.sh`.

## Fast verification

From `web/`:

- `node --test tests/*.test.mjs`
- `pnpm typecheck`
- `pnpm build`

API/browser smoke should use a fresh production preview when ACP runtime behavior matters:

- `PORT=4046 HOST=127.0.0.1 node web/.output/server/index.mjs` after `pnpm --dir web build`
- `curl http://127.0.0.1:4046/api/acp/health`
- browser smoke: app renders, sidebar loads, chat opens, prompt streams, no `/api/web-chat/*` requests.

## Doc maintenance

- Update this map when modules move, new focused helpers/composables become the preferred entrypoint, high-token hotspots change materially, or verification commands change.
- Update `README.md` when setup, development workflow, implemented behavior, or verification guidance changes.
- Update the active `.hermes/plans/*.md` file when completing or materially changing a planned refactor slice.
- Do not edit docs mechanically for tiny local changes that do not affect future agent navigation or developer workflow.

## Safety

- Do not edit `$HOME/.hermes/hermes-agent` directly without explicit approval.
- Do not treat `.runtime/`, `.nuxt/`, `.output/`, or `node_modules/` as source.
