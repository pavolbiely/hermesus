# Hermesum Agent Map

Use this before broad repository search.

## Canonical source

- `backend/hermes_cli/web_chat.py`: backend entrypoint and compatibility wrappers.
- `backend/hermes_cli/web_chat_modules/`: backend domain modules, including `session_summaries.py` for cached out-of-band sidebar chat previews.
- `backend/tests/hermes_cli/test_web_chat*.py`: backend tests split by domain.
- `web/app/pages/chat/[id].vue`: main chat route/page orchestrator.
- `web/app/components/`: chat UI components.
- `web/app/composables/`: frontend API, run streaming, message/run state.
- `web/app/types/web-chat.ts`: frontend API/event types.
- `.runtime/`: disposable runtime mirror; do not edit as source.

## High-token hotspots

- Chat page: `web/app/pages/chat/[id].vue`.
- Layout/sidebar: `web/app/layouts/default.vue`, `SidebarSessionGroups.vue`.
- Message rendering: `ChatMessageContent.vue`, `useChatRunMessages.ts`.
- Run state: `useActiveChatRuns.ts`, backend `run_manager.py`.
- Backend compatibility: `web_chat.py`.

## Fast verification

Frontend from `web/`:

- `pnpm typecheck`
- `pnpm build`

Backend syntax from repo root:

- `python3 -m py_compile backend/hermes_cli/web_chat.py backend/hermes_cli/web_chat_modules/*.py backend/tests/hermes_cli/test_web_chat*.py backend/tests/hermes_cli/conftest.py backend/tests/hermes_cli/web_chat_test_helpers.py`

Backend pytest must use the runtime mirror flow from `AGENTS.md`.

## Doc maintenance

- Update this map when modules move, new focused helpers/composables become the preferred entrypoint, high-token hotspots change materially, or verification commands change.
- Update `README.md` when setup, development workflow, implemented behavior, or verification guidance changes.
- Update the active `.hermes/plans/*.md` file when completing or materially changing a planned refactor slice.
- Do not edit docs mechanically for tiny local changes that do not affect future agent navigation or developer workflow.

## Safety

- Do not edit `$HOME/.hermes/hermes-agent` directly without explicit approval.
- Do not treat `.runtime/`, `.nuxt/`, `.output/`, or `node_modules/` as source.
