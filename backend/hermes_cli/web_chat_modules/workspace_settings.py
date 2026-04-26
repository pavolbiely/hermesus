"""Project-local workspace settings storage for web chat."""

from __future__ import annotations

import json
import os
import pwd
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException, status
from hermes_state import SessionDB

from .models import WebChatWorkspace

DbFactory = Callable[[], SessionDB]


def ensure_workspace_schema(db: SessionDB) -> None:
    def _do(conn):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS web_chat_workspaces (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                path TEXT NOT NULL UNIQUE,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_web_chat_workspaces_label ON web_chat_workspaces(label COLLATE NOCASE)"
        )

    db._execute_write(_do)


def workspace_from_mapping(value: Any) -> WebChatWorkspace:
    return WebChatWorkspace(
        id=value["id"],
        label=value["label"],
        path=value["path"],
        active=False,
    )


def user_home() -> Path:
    home = Path.home()
    if ".hermes" in home.parts and "profiles" in home.parts:
        try:
            return Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
        except Exception:
            return home.resolve()
    return home.resolve()


def expand_workspace_path(path: str) -> Path:
    if path == "~":
        return user_home()
    if path.startswith("~/"):
        return user_home() / path[2:]
    return Path(path).expanduser()


def normalize_workspace_path(path: str) -> Path:
    candidate = expand_workspace_path(path)
    if not candidate.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Directory does not exist")
    return candidate.resolve()


def portable_workspace_path(path: Path) -> str:
    resolved = path.expanduser().resolve()
    home = user_home()
    try:
        relative = resolved.relative_to(home)
    except ValueError:
        return str(resolved)
    if not relative.parts:
        return "~"
    return f"~/{relative.as_posix()}"


def project_root() -> Path:
    configured = os.environ.get("HERMES_WEB_CHAT_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()

    for start in (Path.cwd().resolve(), Path(__file__).resolve()):
        current = start if start.is_dir() else start.parent
        for parent in (current, *current.parents):
            if parent.name == ".runtime":
                return parent.parent
            if (parent / ".hermes").is_dir() and ((parent / "backend").exists() or (parent / "web").exists()):
                return parent

    return Path.cwd().resolve()


def project_web_chat_settings_path() -> Path:
    return project_root() / ".hermes" / "web-chat" / "settings.json"


def empty_project_settings() -> dict[str, Any]:
    return {"version": 1, "workspaces": []}


def read_legacy_db_workspaces(db_factory: DbFactory, db: SessionDB | None = None) -> list[WebChatWorkspace]:
    db = db or db_factory()
    ensure_workspace_schema(db)
    with db._lock:
        rows = db._conn.execute(
            "SELECT id, label, path FROM web_chat_workspaces ORDER BY label COLLATE NOCASE ASC, created_at ASC"
        ).fetchall()
    return [workspace_from_mapping(row) for row in rows]


def load_project_settings(db_factory: DbFactory) -> dict[str, Any]:
    path = project_web_chat_settings_path()
    if not path.exists():
        migrated = [
            {"id": workspace.id, "label": workspace.label, "path": workspace.path}
            for workspace in read_legacy_db_workspaces(db_factory)
        ]
        settings = {"version": 1, "workspaces": migrated}
        if migrated:
            write_project_settings(settings)
        return settings

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid web chat settings file") from exc

    if not isinstance(data, dict):
        return empty_project_settings()
    workspaces = data.get("workspaces")
    if not isinstance(workspaces, list):
        data["workspaces"] = []
    data.setdefault("version", 1)
    return data


def write_project_settings(settings: dict[str, Any]) -> None:
    path = project_web_chat_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(settings, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def settings_workspace_entries(settings: dict[str, Any]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for item in settings.get("workspaces", []):
        if not isinstance(item, dict):
            continue
        try:
            entries.append({"id": str(item["id"]), "label": str(item["label"]), "path": str(item["path"])})
        except KeyError:
            continue
    return entries


def workspace_entries(settings: dict[str, Any]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for item in settings_workspace_entries(settings):
        entries.append({
            "id": item["id"],
            "label": item["label"],
            "path": str(expand_workspace_path(item["path"]).resolve()),
        })
    return entries


