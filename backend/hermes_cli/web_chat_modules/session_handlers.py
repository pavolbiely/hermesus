"""Session endpoint orchestration helpers for the web-chat API."""

from __future__ import annotations

import json
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


def list_sessions_response(
    db: SessionDB,
    *,
    limit: int,
    offset: int,
    list_non_empty_sessions: Callable[[SessionDB, int, int], list[dict[str, Any]]],
    serialize_session: Callable[[dict[str, Any]], WebChatSession],
) -> SessionListResponse:
    sessions = list_non_empty_sessions(db, limit, offset)
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
    )


def rename_session_response(
    db: SessionDB,
    *,
    session_id: str,
    payload: RenameSessionRequest,
    get_session_or_404: Callable[[SessionDB, str], dict[str, Any]],
    serialize_session: Callable[[dict[str, Any]], WebChatSession],
    serialize_messages: Callable[..., list[WebChatMessage]],
) -> SessionDetailResponse:
    get_session_or_404(db, session_id)
    if payload.title is None and payload.pinned is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No session changes provided")

    if payload.title is not None:
        try:
            db.set_session_title(session_id, payload.title)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if payload.pinned is not None:
        _update_session_model_config(db, session_id, {"pinned": True if payload.pinned else None})

    session = get_session_or_404(db, session_id)
    return SessionDetailResponse(
        session=serialize_session(session),
        messages=serialize_messages(db.get_messages(session_id)),
    )


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
    get_session_or_404(db, session_id)
    edit_user_message(db, session_id, message_id, payload.content)
    session = get_session_or_404(db, session_id)
    return SessionDetailResponse(
        session=serialize_session(session),
        messages=serialize_messages(db.get_messages(session_id)),
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
    get_session_or_404: Callable[[SessionDB, str], dict[str, Any]],
    session_git_changes_by_message: Callable[[SessionDB, str], dict[str, WebChatWorkspaceChanges]],
    serialize_session: Callable[[dict[str, Any]], WebChatSession],
    serialize_messages: Callable[..., list[WebChatMessage]],
    active_run_for_session: Callable[[str], Any | None] | None = None,
    isolated_worktree_for_session: Callable[[SessionDB, str], Any | None] | None = None,
) -> SessionDetailResponse:
    session = get_session_or_404(db, session_id)
    messages = db.get_messages(session_id)
    changes_by_message = session_git_changes_by_message(db, session_id) if include_workspace_changes else None
    return SessionDetailResponse(
        session=serialize_session(session),
        messages=serialize_messages(messages, changes_by_message=changes_by_message),
        activeRun=active_run_for_session(session_id) if active_run_for_session else None,
        isolatedWorkspace=isolated_worktree_for_session(db, session_id) if isolated_worktree_for_session else None,
    )
