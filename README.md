# Hermes Agent Nuxt Chat Prototype

This directory contains the project-local prototype for a native Nuxt UI chat interface for Hermes Agent.

## Preview

<p>
  <img src="docs/assets/agent1.png" alt="Hermes Agent chat preview" width="49%">
  <img src="docs/assets/agent2.png" alt="Hermes Agent workspace changes preview" width="49%">
</p>

Do **not** edit `$HOME/.hermes/hermes-agent` directly during prototype work. Treat this repository as the source of truth and move changes with normal git workflow.

## Layout

```text
backend/
  hermes_cli/web_chat.py                    # FastAPI router entrypoint and domain orchestration
  hermes_cli/web_chat_modules/              # extracted web-chat route registration, agent execution, capabilities, profiles, commands, models, sessions/session handlers, session/message mutations, git changes/patches/persistence, workspace/settings, attachment, and run lifecycle helpers
  tests/hermes_cli/test_web_chat*.py        # web-chat pytest coverage split by domain
web/                                        # Nuxt UI prototype
  app/components/WorkspaceModal.vue         # workspace create/edit modal
  app/components/SidebarSessionGroups.vue   # sidebar workspace groups and chat row actions
  app/components/ChatMessageContent.vue      # chat message rendering and user-message actions
  app/components/ChatSlashCommandMenu.vue    # slash-command autocomplete menu
  app/components/ChatAttachmentList.vue      # composer attachment chips
  app/components/ToolCallDetailSection.vue   # tool-call detail modal payload section
  app/composables/useChatRunMessages.ts      # chat run streaming message state and autoscroll handling
  app/composables/useChatSlashCommandSubmission.ts # slash-command submit and keyboard handling
  app/composables/useChatMessageEditing.ts   # user-message edit state, layout, and rerun handling
  app/components/ChatRenameModal.vue        # chat rename modal
  app/components/ChatConfirmActionModal.vue # chat duplicate/delete confirmation modal
  app/utils/chatMessages.ts                 # pure chat message formatting/grouping helpers
  app/utils/toolCallDetails.ts              # pure tool-call detail formatting helpers
  app/utils/clipboard.ts                    # clipboard helper used by chat actions
```

Keep `README.md` updated as the prototype changes, including project structure, setup, workflow, implemented behavior, and verification commands.

## Implemented backend prototype

- `GET /api/web-chat/sessions`
- `POST /api/web-chat/sessions`
- `GET /api/web-chat/sessions/{session_id}`
- `POST /api/web-chat/runs`
- `GET /api/web-chat/runs/{run_id}/events` via SSE
- `POST /api/web-chat/runs/{run_id}/stop`
- `POST /api/web-chat/attachments`
- `GET /api/web-chat/attachments/{attachment_id}`
- `GET /api/web-chat/attachments/{attachment_id}/content`
- `GET /api/web-chat/commands`
- `POST /api/web-chat/commands/execute`

Slash commands are backed by a small backend allowlist. Implemented commands are `/help`, `/status`, and `/changes`; `/clear` is advertised as confirmation-required but is not executed until a confirmation UX exists. Slash commands do not run arbitrary shell commands, and mutating or dangerous commands must remain blocked unless they have explicit backend validation and confirmation.

Chat attachments uploaded through the web UI are stored in the selected project under `.hermes/attachments/`, which is ignored by git in this prototype. Existing filenames are preserved when possible and automatically suffixed instead of overwritten. Image attachments render as inline thumbnails with a larger preview; other files open inline through the authenticated content endpoint when the browser supports their MIME type. Persisted attachment URLs include workspace context on the client side so previews can still be fetched after backend/runtime state is reset. Deleted files remain visible in chat history as unavailable placeholders; deleting a chat does not remove attachment files. Current limits are 8 files per upload request and 25 MB per file.

The run executor is intentionally injectable. The current default emits a placeholder assistant response; wiring to the real `AIAgent` should happen only after explicit approval to integrate these changes into the real Hermes repo or in a disposable worktree.

## Implemented Nuxt prototype

- Nuxt 4 static SPA in `web/`.
- Nuxt UI dashboard shell/sidebar.
- New chat page.
- Chat detail page using `UChatMessages`, `UChatPrompt`, `UChatPromptSubmit`, `UChatReasoning`, `UChatTool`, and `Comark`.
- EventSource/SSE composable for run streaming and stop handling.
- Authenticated `$fetch` helper using injected `window.__HERMES_SESSION_TOKEN__`.
- Slash-command autocomplete in the chat composer when the message starts with `/`.

## Development workflow

Use fast dev mode for normal work, and static mode only when you need to verify the Hermes-served production-style bundle.

### 1. Fast dev mode for frontend + Python development

Use this for day-to-day iteration:

```bash
./run-local.sh --dev
```

Then open `http://127.0.0.1:3019/`. In dev mode, opening the Hermes backend URL (`http://127.0.0.1:9119/`) redirects browser UI requests to the Nuxt dev server so you do not accidentally view stale static output.

What this does:

- Starts the Hermes backend/dashboard runtime on `http://127.0.0.1:9119`.
- Starts Nuxt dev server on `http://127.0.0.1:3019`.
- Proxies Nuxt `/api/...` requests to the Hermes backend.
- Shares an ephemeral dev session token between Nuxt and Hermes so API and SSE calls are authenticated.
- Picks up `web/app/**` changes through Nuxt/Vite HMR without rebuilding the static app.
- Restarts the Hermes backend when watched Python files change.

Useful environment overrides:

```bash
PORT=9120 WEB_DEV_PORT=3020 ./run-local.sh --dev
```

If a previous dev run left listeners behind on the configured ports, the runner waits briefly for them to exit and then force-stops only the stale port listeners. Adjust `PORT_STOP_TIMEOUT` if a local machine needs a longer shutdown grace period.

Important behavior:

- Frontend changes should not trigger `pnpm build`.
- Python changes restart the backend process, so in-flight chats/SSE streams can be interrupted.
- The upstream Hermes checkout is only copied from; runtime patches are applied under `.runtime/hermes-agent`.

### 2. Nuxt-only watch mode for isolated frontend work

Use this when editing files under `web/` and you only need Nuxt itself:

```bash
cd web
pnpm install
pnpm dev
```

Nuxt starts on `http://127.0.0.1:3019/`.

- Changes in `web/app/**` are picked up automatically via Nuxt/Vite HMR.
- You do not need to rerun the command after each change.
- API requests use same-origin `/api/...`; for working Hermes APIs, prefer `./run-local.sh --dev`.

### 3. Hermes-integrated static preview

Use this when you want to launch the disposable Hermes runtime and serve the built Nuxt app through Hermes:

```bash
./run-local.sh
```

Important behavior:

- `run-local.sh` does not run Nuxt in watch mode.
- It installs dependencies if needed and serves the built output from `web/.output/public`.
- If you change frontend files while `run-local.sh` is already running, those changes will not appear until you rebuild and restart.

### 4. Backend watch mode for static Python changes

Use this when you are editing Python files and want Hermes to restart automatically:

```bash
./run-local.sh --watch
```

Important behavior:

- This watches Python files in `backend/` and in the upstream Hermes checkout from `HERMES_AGENT_SOURCE` or `$HOME/.hermes/hermes-agent`.
- When a watched `.py` file changes, the Hermes dashboard process is restarted automatically.
- This is an autorestart loop, not hot module replacement. Existing in-memory session state is lost on each restart.
- Frontend files are still static in this mode. For live frontend refresh, keep using `pnpm dev` in `web/`.

If you need to refresh the static build manually:

```bash
cd web
pnpm build
```

Then stop and start `./run-local.sh` again.

### Recommended day-to-day loop

For normal UI and Python development:

1. Run `./run-local.sh --dev`.
2. Open `http://127.0.0.1:3019/`.
3. Keep that process running while editing.
4. Use `./run-local.sh` only when you specifically need to verify the Hermes-served static integration.

## Verification run

Backend verified by applying the prototype into a temporary local clone of `$HOME/.hermes/hermes-agent`, using the real Hermes venv, and deleting the temporary clone afterwards:

```bash
6 passed in 1.12s
```

Frontend verification from `web/`:

```bash
pnpm typecheck
# exit 0, with existing vue-router/volar package export warning

pnpm build
# Build complete
```

Real Hermes repo cleanliness check after verification:

```bash
git -C "$HOME/.hermes/hermes-agent" status --short
# M web/package-lock.json
```

Only the pre-existing `web/package-lock.json` change remains in the real Hermes repo.
