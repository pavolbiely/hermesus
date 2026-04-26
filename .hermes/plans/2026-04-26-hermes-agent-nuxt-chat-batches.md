# Hermes Agent Nuxt Chat — Batch Plan

Implementation workspace: `/Users/pavolbiely/Sites/hermesum/.hermes/implementation/hermes-agent-nuxt-chat`.

The real Hermes repo `/Users/pavolbiely/.hermes/hermes-agent` must remain untouched during prototype work. Export backend integration as patch files only.

## Estimated batches

Approximately **7 batches** for a usable prototype, **9 batches** including polish/release wiring.

### Batch 1 — Backend API contract prototype
- Keep/clean the current backend prototype files.
- Normalize response types to the planned `WebChatSession` / `WebChatMessage` shape.
- Keep router wiring as a patch file, not applied to the real repo.
- Verification target: copied tests are syntactically valid against Hermes repo when applied.

### Batch 2 — Backend run streaming prototype
- Add run manager design/code for start-run, SSE events, stop.
- Use Hermes `SessionDB` and agent execution references from existing API gateway.
- Export patch files only.

### Batch 3 — Nuxt skeleton in project workspace
- Create `.hermes/implementation/hermes-agent-nuxt-chat/web-nuxt/`.
- Use Nuxt 4 + Nuxt UI + Comark.
- Do not import NuxtHub/Drizzle/auth/provider/demo tools from template.

### Batch 4 — Nuxt layout + session sidebar
- Port dashboard shell pattern from Nuxt UI template.
- Implement sessions composable against `/api/web-chat/sessions`.
- Render grouped sessions/sidebar.

### Batch 5 — Chat pages + prompt UI
- Implement new chat page and session chat page.
- Use `UChatMessages`, `UChatPrompt`, `UChatPromptSubmit`, markdown content.
- Connect create-session and detail endpoints.

### Batch 6 — Streaming UI integration
- Add EventSource/SSE client.
- Render assistant text, reasoning, tool events, stop state.
- Add error/retry states.

### Batch 7 — Local verification package
- Add README/apply instructions.
- Verify generated prototype build/lint where possible.
- Verify real Hermes repo is still unchanged except pre-existing user changes.

### Optional Batch 8 — Real repo patch packaging
- Consolidate backend patch set.
- Add frontend build/static-serving patch proposal.
- Keep as `.patch` files and docs until explicitly approved to apply.

### Optional Batch 9 — Polish/parity pass
- Keyboard UX, empty states, responsive layout, theme alignment.
- Parity checklist against current dashboard flows.
