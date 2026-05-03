"""Session mutation helpers for the web chat API."""

from __future__ import annotations

import json
from typing import Any, Callable
from uuid import uuid4

from hermes_state import SessionDB

from .models import SessionDetailResponse, WebChatSession, WebChatWorkspaceChanges, WebChatMessage
from .sessions import MESSAGE_ITEMS_FIELD, session_with_visible_root_title


def title_from_message(message: str) -> str:
    text = " ".join(message.split())
    return text[:80] or "New chat"


def set_session_title_safely(db: SessionDB, session_id: str, title: str) -> None:
    try:
        db.set_session_title(session_id, title)
    except ValueError:
        suffix = session_id[:6]
        trimmed = title[: max(1, 80 - len(suffix) - 4)]
        db.set_session_title(session_id, f"{trimmed} #{suffix}")


def unique_copy_title(db: SessionDB, title: str | None, session_id: str) -> str:
    base = " ".join((title or "Untitled chat").split()).strip() or "Untitled chat"
    for index in range(1, 100):
        suffix = " copy" if index == 1 else f" copy {index}"
        candidate = f"{base}{suffix}"
        if len(candidate) > 80:
            candidate = f"{base[:80 - len(suffix)]}{suffix}"
        try:
            db.set_session_title(session_id, candidate)
            return candidate
        except ValueError:
            continue
    fallback = f"{base[:69]} {session_id[:10]}"[:80]
    db.set_session_title(session_id, fallback)
    return fallback


def duplicate_session(
    db: SessionDB,
    session_id: str,
    *,
    get_session_or_404: Callable[[SessionDB, str], dict[str, Any]],
    parse_jsonish: Callable[[Any], Any],
    copy_session_git_changes: Callable[..., None],
    session_git_changes_by_message: Callable[[SessionDB, str], dict[str, WebChatWorkspaceChanges]],
    serialize_session: Callable[[dict[str, Any]], WebChatSession],
    serialize_messages: Callable[..., list[WebChatMessage]],
    web_chat_source: str,
) -> SessionDetailResponse:
    session = get_session_or_404(db, session_id)
    new_session_id = uuid4().hex
    model_config = None
    if session.get("model_config"):
        try:
            parsed = json.loads(session["model_config"])
        except (TypeError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, dict):
            model_config = parsed
            model_config.pop("pinned", None)
            model_config.pop("archived", None)
            model_config.pop("restoredAt", None)

    db.create_session(
        new_session_id,
        source=session.get("source") or web_chat_source,
        model=session.get("model"),
        model_config=model_config,
        system_prompt=session.get("system_prompt"),
    )
    unique_copy_title(db, session.get("title") or session.get("preview") or "Untitled chat", new_session_id)

    message_id_map: dict[int, int] = {}
    for message in db.get_messages(session_id):
        new_message_id = db.append_message(
            new_session_id,
            message.get("role"),
            message.get("content"),
            tool_name=message.get("tool_name"),
            tool_calls=message.get("tool_calls"),
            tool_call_id=message.get("tool_call_id"),
            token_count=message.get("token_count"),
            finish_reason=message.get("finish_reason"),
            reasoning=message.get("reasoning"),
            reasoning_content=message.get("reasoning_content"),
            reasoning_details=parse_jsonish(message.get("reasoning_details")),
            codex_reasoning_items=parse_jsonish(message.get("codex_reasoning_items")),
            codex_message_items=parse_jsonish(message.get(MESSAGE_ITEMS_FIELD)),
        )
        if message.get("id") is not None:
            message_id_map[int(message["id"])] = int(new_message_id)

    copy_session_git_changes(
        db,
        source_session_id=session_id,
        target_session_id=new_session_id,
        message_id_map=message_id_map,
    )
    changes_by_message = session_git_changes_by_message(db, new_session_id)

    duplicated = get_session_or_404(db, new_session_id)
    return SessionDetailResponse(
        session=serialize_session(duplicated),
        messages=serialize_messages(db.get_messages(new_session_id), changes_by_message=changes_by_message),
    )


def session_with_tip_config(db: SessionDB, session: dict[str, Any]) -> dict[str, Any]:
    if not session.get("_lineage_root_id"):
        return session

    tip_session_id = session.get("id")
    if not isinstance(tip_session_id, str) or not tip_session_id:
        return session

    tip_session = db._get_session_rich_row(tip_session_id)
    if not tip_session:
        return session

    root_session_id = session.get("_lineage_root_id")
    root_session = db._get_session_rich_row(str(root_session_id)) if root_session_id else None
    visible_session = session_with_visible_root_title(db, session)
    if root_session and root_session.get("title"):
        visible_session = {**visible_session, "title": root_session.get("title")}

    return {**visible_session, "model_config": tip_session.get("model_config")}


def list_non_empty_sessions(
    db: SessionDB,
    limit: int,
    offset: int,
    *,
    max_session_limit: int,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    db_offset = 0
    batch_size = max_session_limit

    while len(sessions) < max_session_limit:
        batch = db.list_sessions_rich(limit=batch_size, offset=db_offset)
        if not batch:
            break
        for session in batch:
            if session.get("message_count", 0) <= 0:
                continue
            session = session_with_tip_config(db, session)
            if not include_archived and _session_archived(session):
                continue
            sessions.append(session)
            if len(sessions) >= max_session_limit:
                break
        db_offset += len(batch)

    sessions.sort(key=_session_last_active_sort_key)
    return sessions[offset:offset + limit]


def _session_last_active_sort_key(session: dict[str, Any]) -> tuple[int, float, float, str]:
    activity = max(
        _numeric_timestamp(session.get("last_active")),
        _numeric_timestamp(_session_model_config(session).get("restoredAt")),
    )
    return (
        0 if _session_pinned(session) else 1,
        -activity,
        -_numeric_timestamp(session.get("started_at")),
        str(session.get("id") or ""),
    )


def _numeric_timestamp(value: Any) -> float:
    return value if isinstance(value, (int, float)) else 0.0


def _session_model_config(session: dict[str, Any]) -> dict[str, Any]:
    raw = session.get("model_config")
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _session_pinned(session: dict[str, Any]) -> bool:
    return _session_model_config(session).get("pinned") is True


def _session_archived(session: dict[str, Any]) -> bool:
    return _session_model_config(session).get("archived") is True
