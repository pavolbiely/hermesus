# Applying the Prototype to Hermes Agent Later

This prototype intentionally lives outside the real Hermes Agent checkout.

## Current source of truth

```text
/Users/pavolbiely/Sites/hermesum/.hermes/implementation/hermes-agent-nuxt-chat
```

## Safety check before applying anything

```bash
git -C /Users/pavolbiely/.hermes/hermes-agent status --short
```

Do not apply patches if unrelated local work is present unless it is explicitly accounted for.

## Backend patch application

From the real Hermes repo, after explicit approval:

```bash
cd /Users/pavolbiely/.hermes/hermes-agent
git apply /Users/pavolbiely/Sites/hermesum/.hermes/implementation/hermes-agent-nuxt-chat/backend/patches/backend-web-chat-combined.patch
venv/bin/python -m pytest tests/hermes_cli/test_web_chat.py -q
```

## Frontend copy/application

The Nuxt prototype is currently a standalone folder:

```text
web-nuxt/
```

A later integration patch should decide whether Hermes should:

1. add this as `web-nuxt/` next to the current React `web/`, or
2. replace the existing `web/` only after parity is accepted.

Recommended next step: keep both and serve Nuxt via an explicit `HERMES_WEB_DIST` path during testing.

## Verified commands in project-local prototype

```bash
# backend patch test, run in temporary clone
6 passed in 1.12s

# frontend
pnpm typecheck
pnpm build
```
