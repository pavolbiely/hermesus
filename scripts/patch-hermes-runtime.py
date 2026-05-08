#!/usr/bin/env python3
"""Patch a disposable Hermes runtime so Hermesum web-chat tests can run."""

from __future__ import annotations

import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ.get("HERMES_RUNTIME_PATH", ROOT / ".runtime" / "hermes-agent"))


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Could not patch {label}: expected text not found")
    return text.replace(old, new, 1)


def patch_web_server() -> None:
    path = RUNTIME / "hermes_cli" / "web_server.py"
    text = path.read_text()

    if "from hermes_cli.web_chat import router as web_chat_router" not in text:
        needle = 'WEB_DIST = Path(os.environ["HERMES_WEB_DIST"]) if "HERMES_WEB_DIST" in os.environ else Path(__file__).parent / "web_dist"'
        text = replace_once(
            text,
            needle,
            'from hermes_cli.web_chat import router as web_chat_router\n\n' + needle,
            label="web-chat router import",
        )

    if "app.include_router(web_chat_router)" not in text:
        text = replace_once(
            text,
            "# Mount plugin API routes before the SPA catch-all.\n_mount_plugin_api_routes()",
            "# Mount built-in and plugin API routes before the SPA catch-all.\napp.include_router(web_chat_router)\n_mount_plugin_api_routes()",
            label="web-chat router mount",
        )

    if 'request.query_params.get("session_token", "")' not in text:
        needle = """    if session_header and hmac.compare_digest(\n        session_header.encode(),\n        _SESSION_TOKEN.encode(),\n    ):\n        return True\n\n"""
        replacement = needle + """    if request.url.path.startswith("/api/web-chat/runs/") and request.url.path.endswith("/events"):\n        session_token = request.query_params.get("session_token", "")\n        if session_token and hmac.compare_digest(session_token.encode(), _SESSION_TOKEN.encode()):\n            return True\n\n"""
        text = replace_once(text, needle, replacement, label="SSE session-token auth")

    env_name = "HERMES_" + "SESSION_" + "TOKEN"
    if f'os.environ.get("{env_name}")' not in text:
        text, count = re.subn(
            r"_SESSION_TOKEN\s*=\s*secrets\.token_urlsafe\(\d+\)",
            f'_SESSION_TOKEN = os.environ.get("{env_name}") or secrets.token_urlsafe(32)',
            text,
            count=1,
        )
        if count != 1:
            raise RuntimeError("Could not patch Hermes web session token override")

    path.write_text(text)


def patch_hermes_state() -> None:
    path = RUNTIME / "hermes_state.py"
    text = path.read_text()

    if "def update_session_model_settings(" in text:
        return

    needle = """    def update_system_prompt(self, session_id: str, system_prompt: str) -> None:\n        \"\"\"Store the full assembled system prompt snapshot.\"\"\"\n        def _do(conn):\n            conn.execute(\n                \"UPDATE sessions SET system_prompt = ? WHERE id = ?\",\n                (system_prompt, session_id),\n            )\n        self._execute_write(_do)\n"""
    replacement = needle + '''

    def update_session_model_settings(
        self,
        session_id: str,
        *,
        model: Optional[str] = None,
        model_config_updates: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update session-level model settings while preserving other config."""

        def _do(conn):
            cursor = conn.execute(
                "SELECT model_config FROM sessions WHERE id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            model_config: Dict[str, Any] = {}
            if row and row["model_config"]:
                try:
                    parsed = json.loads(row["model_config"])
                except Exception:
                    parsed = None
                if isinstance(parsed, dict):
                    model_config = parsed

            if model_config_updates:
                for key, value in model_config_updates.items():
                    if value is None:
                        model_config.pop(key, None)
                    else:
                        model_config[key] = value

            conn.execute(
                """UPDATE sessions
                   SET model = COALESCE(?, model),
                       model_config = ?
                   WHERE id = ?""",
                (
                    model,
                    json.dumps(model_config) if model_config else None,
                    session_id,
                ),
            )

        self._execute_write(_do)
'''
    path.write_text(replace_once(text, needle, replacement, label="SessionDB model settings"))


def main() -> None:
    if not RUNTIME.exists():
        raise SystemExit(f"Runtime checkout does not exist: {RUNTIME}")

    patch_web_server()
    patch_hermes_state()


if __name__ == "__main__":
    main()
