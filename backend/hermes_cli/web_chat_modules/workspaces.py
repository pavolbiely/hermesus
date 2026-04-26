"""Managed workspace settings helpers for the web chat API."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from fastapi import HTTPException, status
from hermes_state import SessionDB

from .models import SaveWorkspaceRequest, WebChatWorkspace, WebChatWorkspacesResponse

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


def normalize_workspace_path(path: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Directory does not exist")
    return candidate.resolve()


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


def workspace_entries(settings: dict[str, Any]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for item in settings.get("workspaces", []):
        if not isinstance(item, dict):
            continue
        try:
            entries.append({"id": str(item["id"]), "label": str(item["label"]), "path": str(item["path"])})
        except KeyError:
            continue
    return entries


def list_managed_workspaces(db_factory: DbFactory, settings_lock: threading.Lock, db: SessionDB | None = None) -> list[WebChatWorkspace]:
    del db
    with settings_lock:
        entries = workspace_entries(load_project_settings(db_factory))
    return sorted(
        (workspace_from_mapping(entry) for entry in entries),
        key=lambda workspace: (workspace.label.lower(), workspace.label, workspace.path),
    )


def find_managed_workspace_by_path(
    path: Path,
    db_factory: DbFactory,
    settings_lock: threading.Lock,
    db: SessionDB | None = None,
) -> WebChatWorkspace | None:
    del db
    resolved = str(path.resolve())
    with settings_lock:
        for entry in workspace_entries(load_project_settings(db_factory)):
            if entry["path"] == resolved:
                return workspace_from_mapping(entry)
    return None


def get_managed_workspace(
    workspace_id: str,
    db_factory: DbFactory,
    settings_lock: threading.Lock,
    db: SessionDB | None = None,
) -> WebChatWorkspace:
    del db
    with settings_lock:
        for entry in workspace_entries(load_project_settings(db_factory)):
            if entry["id"] == workspace_id:
                return workspace_from_mapping(entry)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")


def create_managed_workspace(request: SaveWorkspaceRequest, db_factory: DbFactory, settings_lock: threading.Lock) -> WebChatWorkspace:
    path = str(normalize_workspace_path(request.path))
    workspace_id = uuid4().hex
    label = request.label.strip()

    with settings_lock:
        settings = load_project_settings(db_factory)
        entries = workspace_entries(settings)
        if any(entry["path"] == path for entry in entries):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Workspace path already exists")
        workspace = {"id": workspace_id, "label": label, "path": path}
        settings["workspaces"] = [*entries, workspace]
        write_project_settings(settings)

    return workspace_from_mapping(workspace)


def update_managed_workspace(
    workspace_id: str,
    request: SaveWorkspaceRequest,
    db_factory: DbFactory,
    settings_lock: threading.Lock,
) -> WebChatWorkspace:
    path = str(normalize_workspace_path(request.path))
    label = request.label.strip()

    with settings_lock:
        settings = load_project_settings(db_factory)
        entries = workspace_entries(settings)
        existing = next((entry for entry in entries if entry["id"] == workspace_id), None)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
        if any(entry["id"] != workspace_id and entry["path"] == path for entry in entries):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Workspace path already exists")

        updated = {"id": workspace_id, "label": label, "path": path}
        settings["workspaces"] = [updated if entry["id"] == workspace_id else entry for entry in entries]
        write_project_settings(settings)

    return workspace_from_mapping(updated)


def workspace_label(path: Path) -> str:
    return path.name or str(path)


def validate_workspace(
    workspace: str | None,
    *,
    find_managed_workspace_by_path_func: Callable[[Path], WebChatWorkspace | None],
    workspace_root_func: Callable[[str | None], Path | None],
) -> Path | None:
    if not workspace:
        return None
    candidate = Path(workspace).expanduser()
    if not candidate.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Directory does not exist")

    resolved = candidate.resolve()
    if find_managed_workspace_by_path_func(resolved):
        return resolved

    root = workspace_root_func(str(candidate))
    if root:
        return root.resolve()

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Directory is not a managed or git workspace")


def list_web_chat_workspaces(list_managed_workspaces_func: Callable[[], list[WebChatWorkspace]]) -> WebChatWorkspacesResponse:
    return WebChatWorkspacesResponse(workspaces=list_managed_workspaces_func(), activeWorkspace=None)


def directory_suggestions(prefix: str, *, limit: int = 300) -> list[str]:
    value = prefix.strip()
    if not value:
        return []

    expanded = Path(value).expanduser()
    if expanded.is_dir():
        parent = expanded
        name_prefix = ""
    else:
        parent = expanded.parent
        name_prefix = expanded.name

    if str(parent) in {"", "."} or not parent.is_dir():
        return []

    try:
        children = sorted(
            (child for child in parent.iterdir() if child.is_dir() and child.name.startswith(name_prefix)),
            key=lambda child: child.name.lower(),
        )
    except OSError:
        return []

    seen: set[str] = set()
    suggestions: list[str] = []
    for child in children:
        resolved = str(child.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        suggestions.append(resolved)
        if len(suggestions) >= limit:
            break
    return suggestions


def default_workspace(list_workspaces_func: Callable[[], WebChatWorkspacesResponse]) -> Path | None:
    active = list_workspaces_func().activeWorkspace
    return Path(active) if active else None


def delete_managed_workspace(workspace_id: str, db_factory: DbFactory, settings_lock: threading.Lock) -> None:
    with settings_lock:
        settings = load_project_settings(db_factory)
        entries = workspace_entries(settings)
        if not any(entry["id"] == workspace_id for entry in entries):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
        settings["workspaces"] = [entry for entry in entries if entry["id"] != workspace_id]
        write_project_settings(settings)
