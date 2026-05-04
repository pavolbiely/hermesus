# AGENTS.md

## Project Overview

This repository is the project-local prototype for a native Nuxt UI chat interface and FastAPI web-chat API for Hermes Agent.

Treat this repository as the source of truth for prototype work. Do not edit `$HOME/.hermes/hermes-agent` directly unless the user explicitly approves it. Runtime integration should happen through the disposable `.runtime/hermes-agent` copy created by `run-local.sh`.

## Repository Map

- `backend/hermes_cli/web_chat.py`: FastAPI web-chat entrypoint; keep it thin (router creation, public compatibility wrappers, dependency wiring).
- `backend/hermes_cli/web_chat_modules/`: modular backend implementation split by domain: route registration, Pydantic models, run lifecycle, agent execution, sessions, session handlers, session/message mutations, commands, capabilities, profiles, attachments, workspaces/settings, git changes/patches/persistence.
- `backend/tests/hermes_cli/test_web_chat*.py`: pytest coverage split by backend web-chat domain; shared fixtures/helpers live beside the split tests.
- `web/`: Nuxt 4 static SPA prototype using Nuxt UI and Comark.
- `web/app`: Nuxt application code, pages, components, composables, types, and assets.
- `run-local.sh`: local orchestration for Hermes backend runtime, Nuxt dev mode, and static preview.
- `.runtime/`: disposable generated/runtime state. Do not treat it as source code.

## Core Engineering Rules

- Prefer small, clear, maintainable changes over clever or broad rewrites.
- Understand existing flow before changing code, especially backend run execution, SSE streaming, session persistence, and runtime patching.
- Keep code reusable where reuse is real, but avoid generic abstractions for one-off prototype code.
- Favor focused modules, typed boundaries, explicit validation, and predictable error handling.
- Prefer project-native and framework-native APIs before adding new dependencies.
- Do not couple prototype code unnecessarily to local machine paths beyond documented Hermes integration points.
- Keep `README.md` updated when project structure, setup, development workflow, implemented behavior, or verification commands change.
- Keep `.hermes/agent-map.md` updated when code boundaries, high-token hotspots, first-read files, or verification entrypoints change.
- Keep the active `.hermes/plans/*.md` file updated when completing or materially changing a planned refactor slice; avoid creating overlapping plans for the same work.
- Do not update project docs mechanically after every small edit. Update `AGENTS.md`, `.hermes/agent-map.md`, `README.md`, and active plans only when the change affects future agent navigation, architecture boundaries, setup/workflow, behavior, or verification.
- Do not add new large catch-all files. When a file starts mixing unrelated concerns or grows past a comfortable review size, split it into cohesive modules before adding more behavior.
- Keep the source tree clean: do not commit generated `.nuxt`, `.output`, `node_modules`, runtime copies, logs, or disposable verification artifacts.

## Architecture Boundaries

- `backend/` contains proposed Hermes backend additions. Keep this code portable enough to move into the real Hermes Agent repository later.
- `web/` contains the Nuxt UI prototype. Keep frontend code independent from backend internals except through documented `/api/web-chat/*` contracts.
- `run-local.sh` may patch/copy into `.runtime/hermes-agent`; those patches must be reproducible from source files in this repository.
- Shared request/response shapes should remain aligned between Python Pydantic models and TypeScript frontend types.
- When backend payloads change, update Python models, API behavior, frontend types, frontend API helpers, and tests in the same logical change.

## Backend Modularity Rules

The backend web-chat implementation is intentionally modular. Do not regress to a monolithic `web_chat.py` or one huge test file.

- Keep `web_chat.py` as the stable public entrypoint: router instance, constants, compatibility wrappers used by tests/monkeypatching, `RunManager` factory, and service wiring.
- Put route definitions and FastAPI-specific endpoint registration in `web_chat_modules/routes.py`.
- Put Pydantic request/response DTOs in `web_chat_modules/models.py`; do not define new API models inline in route handlers.
- Keep run queue/thread/SSE lifecycle behavior in `web_chat_modules/run_manager.py`.
- Keep agent invocation/conversation-history assembly in `web_chat_modules/agent_runner.py`.
- Keep serialization/parsing of sessions, messages, parts, attachments, and tool calls in `web_chat_modules/sessions.py`.
- Keep session endpoint orchestration in `web_chat_modules/session_handlers.py` and session/message mutation helpers in `session_mutations.py` / `message_mutations.py`.
- Keep slash-command logic in `commands.py`, profile/capability logic in `profiles.py` / `capabilities.py`, attachment storage/lookup in `attachments.py`, workspace/settings logic in `workspaces.py` / `workspace_settings.py`, and git-change behavior in `git_changes.py` / `git_patches.py` / `persisted_git_changes.py`.
- Prefer adding behavior to the closest existing domain module. Create a new focused module only when the behavior does not fit an existing boundary.
- Preserve thin wrappers in `web_chat.py` when existing tests or monkeypatch patterns rely on those names. If an extracted module needs such behavior, pass callbacks/dependencies from `web_chat.py` rather than importing back into it.
- Keep backend web-chat tests split by domain (`test_web_chat_commands.py`, `test_web_chat_attachments.py`, `test_web_chat_workspaces.py`, `test_web_chat_runs.py`, `test_web_chat_run_options.py`, plus core session tests). Move shared setup to `conftest.py` and simple helpers to `web_chat_test_helpers.py`.

## Backend API Rules

The backend web-chat API is a contract surface. Keep it explicit and stable.

- Validate request payloads with Pydantic models.
- Keep response models explicit and serializable.
- Use clear HTTP status codes and avoid leaking internal exception details to the UI.
- Keep route handlers readable: validate input, resolve session/run state, perform action, return a typed response.
- Keep run execution injectable so tests can exercise behavior without invoking the real agent runtime.
- Preserve SSE event format compatibility when changing streaming behavior.
- Always consider stop/cancellation behavior, thread lifecycle, queue cleanup, and client disconnects when touching run streaming.
- Keep session persistence through `SessionDB` as the source of truth unless the architecture is intentionally changed.
- Do not wire to the real `AIAgent` or mutate the real Hermes checkout without explicit approval.

## Frontend Rules

- Use Nuxt 4, Vue 3, TypeScript strict mode, Nuxt UI, and Comark idiomatically.
- Prefer existing Nuxt UI chat/dashboard components before creating custom UI primitives.
- Keep composables focused: API calls, SSE streaming, time formatting, and composer capabilities should stay separated.
- Keep components typed and simple. Avoid broad `any`, implicit event payloads, and hidden assumptions about backend data.
- Prefer computed state over duplicated reactive state.
- Handle loading, empty, error, streaming, stopped, and disconnected states explicitly.
- Keep API access behind composables such as `useHermesApi` and streaming behavior behind `useHermesRunStream`.
- Do not hardcode backend origins in UI code. Use same-origin `/api/...` and the documented dev proxy/runtime config.
- Do not rely on stale static output while developing. Use dev mode for normal UI work.

## Reusability and Extensibility

- Extract reusable frontend behavior into composables only when it is used by multiple views or clearly belongs to a stable API boundary.
- Extract reusable backend behavior into small helpers/classes when it reduces duplication in routes, run management, serialization, or tests.
- Keep extension points around stable concepts: sessions, messages, runs, events, capabilities, workspace changes, and model settings.
- Avoid abstractions based only on current layout or temporary prototype UI structure.
- Prefer explicit option objects for functions likely to grow, but keep simple functions simple.
- Keep frontend TypeScript types close to the API surface they describe.
- When adding new API fields, make defaults/backwards compatibility explicit.

## Development Workflow

Use fast dev mode for normal work:

```sh
./run-local.sh --dev
```

This starts:

- Hermes backend/dashboard runtime on `http://127.0.0.1:9119`.
- Nuxt dev server on `http://127.0.0.1:3019` by default; override bind host with `WEB_DEV_HOST`.
- Nuxt `/api/...` proxy to the Hermes backend.
- Shared ephemeral dev session token for authenticated API/SSE calls.

For isolated frontend work:

```sh
cd web
pnpm install
pnpm dev
```

For Hermes-served static preview:

```sh
./run-local.sh
```

Important behavior:

- Frontend changes in dev mode should use Nuxt/Vite HMR and should not require `pnpm build`.
- Static preview serves built output from `web/.output/public`; rebuild and restart after frontend changes.
- Python changes in watch/dev mode restart the backend process and can interrupt in-flight SSE/chat runs.

## Verification

Prefer the smallest verification command that covers the touched area. Do not claim verification unless it was actually run.

Frontend verification from `web/`:

```sh
pnpm typecheck
pnpm build
```

Backend verification should run syntax checks against canonical sources and pytest against the runtime mirror, because backend tests import the runtime package layout:

```sh
python3 -m py_compile backend/hermes_cli/web_chat.py backend/hermes_cli/web_chat_modules/*.py backend/tests/hermes_cli/test_web_chat*.py backend/tests/hermes_cli/conftest.py backend/tests/hermes_cli/web_chat_test_helpers.py
```

For mirrored runtime pytest, copy canonical backend/test files into `.runtime/hermes-agent` inside the `uv run --no-project ... bash -lc` command immediately before pytest. Target the explicit split web-chat test files (`test_web_chat*.py`), not the whole runtime test directory, to avoid unrelated upstream tests/dependencies.

When verifying integration with the real Hermes runtime:

- Use a temporary/disposable checkout or `.runtime/hermes-agent`.
- Do not leave unintended changes in `$HOME/.hermes/hermes-agent`.
- Check real Hermes checkout cleanliness afterwards if it was involved:

```sh
git -C "$HOME/.hermes/hermes-agent" status --short
```

## Change Coordination Checklist

Before finalizing changes, check:

- Did the change touch this repository root and not `$HOME/.hermes/hermes-agent` or another project?
- Are backend Pydantic models, route behavior, frontend types, and API composables aligned?
- Are SSE event names and payloads still compatible with frontend consumers?
- Are run cancellation, cleanup, and error states handled?
- Are Nuxt UI components used through their intended APIs before custom markup was added?
- Are generated/runtime artifacts excluded from source changes?
- Was the smallest relevant backend/frontend verification run?
- Are any skipped checks or known pre-existing warnings stated clearly?

## Safety Notes

- Do not modify `$HOME/.hermes/hermes-agent` directly without explicit approval.
- Do not perform global package-manager changes or Homebrew install/uninstall actions without explicit approval.
- Do not add secrets or session tokens to committed files.
- Treat runtime patches, copied upstream files, and static build output as disposable unless explicitly promoted into source.
