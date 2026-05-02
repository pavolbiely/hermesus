"""Session endpoint orchestration helpers for the web-chat API."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from fastapi import HTTPException, status
from hermes_state import SessionDB

from .models import (
    CreateSessionRequest,
    DeleteSessionResponse,
    EditMessageRequest,
    RenameSessionRequest,
    SessionDetailResponse,
    SessionListResponse,
    WebChatSession,
    WebChatMessage,
    WebChatWorkspaceChanges,
)
from .sessions import session_archived, session_workspace


def list_sessions_response(
    db: SessionDB,
    *,
    limit: int,
    offset: int,
    include_archived: bool,
    list_non_empty_sessions: Callable[[SessionDB, int, int, bool], list[dict[str, Any]]],
    serialize_session: Callable[[dict[str, Any]], WebChatSession],
) -> SessionListResponse:
    sessions = list_non_empty_sessions(db, limit, offset, include_archived)
    return SessionListResponse(sessions=[serialize_session(session) for session in sessions])


def create_session_response(
    db: SessionDB,
    *,
    payload: CreateSessionRequest,
    web_chat_source: str,
    title_from_message: Callable[[str], str],
    get_session_or_404: Callable[[SessionDB, str], dict[str, Any]],
    serialize_session: Callable[[dict[str, Any]], WebChatSession],
    serialize_messages: Callable[..., list[WebChatMessage]],
) -> SessionDetailResponse:
    session_id = uuid4().hex
    title = title_from_message(payload.message)

    db.create_session(session_id, source=web_chat_source)
    db.set_session_title(session_id, title)
    db.append_message(session_id, "user", payload.message)

    session = get_session_or_404(db, session_id)
    messages = db.get_messages(session_id)
    return SessionDetailResponse(
        session=serialize_session(session),
        messages=serialize_messages(messages),
        compressionCount=compression_count(db, session),
    )


def rename_session_response(
    db: SessionDB,
    *,
    session_id: str,
    payload: RenameSessionRequest,
    get_session_or_404: Callable[[SessionDB, str], dict[str, Any]],
    serialize_session: Callable[[dict[str, Any]], WebChatSession],
    serialize_messages: Callable[..., list[WebChatMessage]],
    validate_workspace: Callable[[str | None], Path | None] | None = None,
) -> SessionDetailResponse:
    session = get_session_or_404(db, session_id)
    provided_fields = getattr(payload, "model_fields_set", None)
    if provided_fields is None:
        provided_fields = getattr(payload, "__fields_set__", set())
    workspace_provided = "workspace" in provided_fields
    if payload.title is None and payload.pinned is None and payload.archived is None and not workspace_provided:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No session changes provided")

    if payload.title is not None:
        try:
            db.set_session_title(session_id, payload.title)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if payload.pinned is not None:
        _update_session_model_config(db, session_id, {"pinned": True if payload.pinned else None})

    if payload.archived is not None or workspace_provided:
        model_config_updates: dict[str, Any] = {}
        if workspace_provided:
            if not payload.workspace:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Workspace is required")
            if not validate_workspace:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Workspace validation is unavailable")
            workspace = validate_workspace(payload.workspace)
            model_config_updates["workspace"] = str(workspace) if workspace else None

        if payload.archived is not None:
            if payload.archived:
                model_config_updates["archived"] = True
                model_config_updates["restoredAt"] = None
            else:
                if not workspace_provided:
                    existing_workspace = session_workspace(session)
                    if existing_workspace and validate_workspace:
                        try:
                            validate_workspace(existing_workspace)
                        except HTTPException as exc:
                            raise HTTPException(
                                status_code=status.HTTP_409_CONFLICT,
                                detail="Workspace no longer exists. Choose another workspace to restore this chat.",
                            ) from exc
                model_config_updates["archived"] = None
                model_config_updates["restoredAt"] = time.time()

        _update_session_model_config(db, session_id, model_config_updates)

    session = get_session_or_404(db, session_id)
    return SessionDetailResponse(
        session=serialize_session(session),
        messages=serialize_messages(db.get_messages(session_id)),
        compressionCount=compression_count(db, session),
    )


def compression_count(db: SessionDB, session: dict[str, Any]) -> int:
    """Count compression continuations from the logical conversation root to this session."""
    count = 0
    for parent, child in compression_lineage_pairs(db, session):
        parent_ended_at = parent.get("ended_at")
        child_started_at = child.get("started_at")
        if (
            parent.get("end_reason") == "compression"
            and isinstance(parent_ended_at, (int, float))
            and isinstance(child_started_at, (int, float))
            and child_started_at >= parent_ended_at
        ):
            count += 1

    return count


def compression_lineage_pairs(db: SessionDB, session: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Return parent/child pairs from the current session back to its root."""
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    current = session
    seen = {str(session.get("id"))}
    for _ in range(100):
        parent_id = current.get("parent_session_id")
        if not parent_id or str(parent_id) in seen:
            return pairs

        parent = db._get_session_rich_row(parent_id)
        if not parent:
            return pairs

        pairs.append((parent, current))
        seen.add(str(parent_id))
        current = parent

    return pairs


def session_lineage(db: SessionDB, session: dict[str, Any]) -> list[dict[str, Any]]:
    """Return root-to-tip sessions for a compressed conversation."""
    parents = [parent for parent, _child in compression_lineage_pairs(db, session)]
    return [*reversed(parents), session]


def session_lineage_messages(db: SessionDB, session: dict[str, Any]) -> list[dict[str, Any]]:
    """Return messages across compressed parent sessions, preserving chat history in the UI."""
    messages: list[dict[str, Any]] = []
    for lineage_session in session_lineage(db, session):
        lineage_session_id = lineage_session.get("id")
        if lineage_session_id:
            messages.extend(db.get_messages(str(lineage_session_id)))
    return messages


def _update_session_model_config(db: SessionDB, session_id: str, updates: dict[str, Any]) -> None:
    update_model_settings = getattr(db, "update_session_model_settings", None)
    if callable(update_model_settings):
        update_model_settings(session_id, model_config_updates=updates)
        return

    def _do(conn: Any) -> None:
        cursor = conn.execute("SELECT model_config FROM sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        config: dict[str, Any] = {}
        if row and row["model_config"]:
            try:
                parsed = json.loads(row["model_config"])
            except Exception:
                parsed = None
            if isinstance(parsed, dict):
                config = parsed

        for key, value in updates.items():
            if value is None:
                config.pop(key, None)
            else:
                config[key] = value

        conn.execute(
            "UPDATE sessions SET model_config = ? WHERE id = ?",
            (json.dumps(config) if config else None, session_id),
        )

    db._execute_write(_do)


def edit_message_response(
    db: SessionDB,
    *,
    session_id: str,
    message_id: str,
    payload: EditMessageRequest,
    get_session_or_404: Callable[[SessionDB, str], dict[str, Any]],
    edit_user_message: Callable[[SessionDB, str, str, str], None],
    serialize_session: Callable[[dict[str, Any]], WebChatSession],
    serialize_messages: Callable[..., list[WebChatMessage]],
) -> SessionDetailResponse:
    session = get_session_or_404(db, session_id)
    if session_archived(session):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Restore archived chat before editing a message.")
    edit_user_message(db, session_id, message_id, payload.content)
    session = get_session_or_404(db, session_id)
    return SessionDetailResponse(
        session=serialize_session(session),
        messages=serialize_messages(db.get_messages(session_id)),
        compressionCount=compression_count(db, session),
    )


def delete_session_response(
    db: SessionDB,
    *,
    session_id: str,
    delete_session_git_changes: Callable[[SessionDB, str], None],
    remove_session_worktree: Callable[[SessionDB, str], None],
) -> DeleteSessionResponse:
    if not db.delete_session(session_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    remove_session_worktree(db, session_id)
    delete_session_git_changes(db, session_id)
    return DeleteSessionResponse(ok=True)


def get_session_response(
    db: SessionDB,
    *,
    session_id: str,
    include_workspace_changes: bool,
    message_limit: int | None = None,
    message_before: str | None = None,
    get_session_or_404: Callable[[SessionDB, str], dict[str, Any]],
    session_git_changes_by_message: Callable[[SessionDB, str], dict[str, WebChatWorkspaceChanges]],
    serialize_session: Callable[[dict[str, Any]], WebChatSession],
    serialize_messages: Callable[..., list[WebChatMessage]],
    active_run_for_session: Callable[[str], Any | None] | None = None,
    recover_interrupted_run_for_session: Callable[[str], None] | None = None,
    isolated_worktree_for_session: Callable[[SessionDB, str], Any | None] | None = None,
) -> SessionDetailResponse:
    session = get_session_or_404(db, session_id)
    active_run = active_run_for_session(session_id) if active_run_for_session else None
    if active_run is None and recover_interrupted_run_for_session:
        recover_interrupted_run_for_session(session_id)
    all_messages = session_lineage_messages(db, session)
    messages_total = len(all_messages)
    messages = window_session_messages(all_messages, limit=message_limit, before_message_id=message_before)
    changes_by_message: dict[str, WebChatWorkspaceChanges] | None = None
    if include_workspace_changes:
        changes_by_message = {}
        for lineage_session in session_lineage(db, session):
            lineage_session_id = lineage_session.get("id")
            if lineage_session_id:
                changes_by_message.update(session_git_changes_by_message(db, str(lineage_session_id)))
    return SessionDetailResponse(
        session=serialize_session(session),
        messages=serialize_messages(messages, changes_by_message=changes_by_message),
        activeRun=active_run,
        isolatedWorkspace=isolated_worktree_for_session(db, session_id) if isolated_worktree_for_session else None,
        compressionCount=compression_count(db, session),
        messagesHasMoreBefore=messages_total > 0 and bool(messages) and all_messages[0].get("id") != messages[0].get("id"),
        messagesTotal=messages_total,
    )


def window_session_messages(
    messages: list[dict[str, Any]],
    *,
    limit: int | None,
    before_message_id: str | None,
) -> list[dict[str, Any]]:
    if limit is None:
        return messages

    end = len(messages)
    if before_message_id:
        end = next((index for index, message in enumerate(messages) if str(message.get("id")) == before_message_id), end)

    start = max(0, end - limit)
    return messages[start:end]
