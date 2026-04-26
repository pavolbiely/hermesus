"""Managed workspace helpers for the web chat API."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable
from uuid import uuid4

from fastapi import HTTPException, status
from hermes_state import SessionDB

from .models import SaveWorkspaceRequest, WebChatWorkspace, WebChatWorkspacesResponse
from .workspace_settings import (
    DbFactory,
    empty_project_settings,
    ensure_workspace_schema,
    load_project_settings,
    normalize_workspace_path,
    project_root,
    project_web_chat_settings_path,
    read_legacy_db_workspaces,
    workspace_entries,
    workspace_from_mapping,
    write_project_settings,
)


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
