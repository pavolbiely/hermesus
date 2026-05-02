"""Out-of-band chat preview summaries for sidebar popovers."""

from __future__ import annotations

import re
import time
from typing import Any, Callable

from fastapi import HTTPException, status
from hermes_state import SessionDB

from .models import WebChatSessionPreviewResponse
from .session_handlers import _update_session_model_config, session_lineage_messages
from .sessions import session_model_config, session_provider, session_reasoning_effort, session_workspace

SIDEBAR_SUMMARY_CONFIG_KEY = "sidebar_summary"
SUMMARY_MAX_CHARS = 700
SUMMARY_INPUT_MAX_CHARS = 60_000

HiddenAgent = Callable[..., str]


def get_session_preview(
    db: SessionDB,
    session_id: str,
    *,
    get_session_or_404: Callable[[SessionDB, str], dict[str, Any]],
) -> WebChatSessionPreviewResponse:
    session = get_session_or_404(db, session_id)
    summary = _stored_summary(session)
    return WebChatSessionPreviewResponse(
        sessionId=session_id,
        summary=summary.get("text") if summary else None,
        summaryStatus="ready" if summary else "missing",
        messageCount=int(session.get("message_count") or 0),
        updatedAt=summary.get("updatedAt") if summary else None,
    )


def generate_session_preview(
    db: SessionDB,
    session_id: str,
    *,
    get_session_or_404: Callable[[SessionDB, str], dict[str, Any]],
    hidden_agent: HiddenAgent,
) -> WebChatSessionPreviewResponse:
    session = get_session_or_404(db, session_id)
    messages = _summary_conversation_history(db, session)
    if not messages:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session has no messages to summarize")

    prompt = (
        "Describe what this Hermes chat is about for a sidebar hover preview.\n"
        f"Maximum {SUMMARY_MAX_CHARS} characters.\n"
        "Use the user's language.\n"
        "Mention the main topic and latest state/outcome when useful.\n"
        "Do not mention that you are summarizing.\n"
        "Do not include secrets, credentials, or raw tool noise.\n"
        "Return only the summary text."
    )
    try:
        text = hidden_agent(
            prompt,
            conversation_history=messages,
            session_id=session_id,
            workspace=session_workspace(session),
            model=session.get("model") or None,
            provider=session_provider(session),
            reasoning_effort=session_reasoning_effort(session),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to generate chat summary") from exc

    summary_text = _clean_summary(text)
    if not summary_text:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Summary generation returned no text")

    now = time.time()
    payload = {
        "text": summary_text,
        "messageCount": int(session.get("message_count") or len(messages)),
        "updatedAt": _iso_from_epoch(now),
        "source": "hidden_hermes",
    }
    _update_session_model_config(db, session_id, {SIDEBAR_SUMMARY_CONFIG_KEY: payload})

    return WebChatSessionPreviewResponse(
        sessionId=session_id,
        summary=summary_text,
        summaryStatus="ready",
        messageCount=payload["messageCount"],
        updatedAt=payload["updatedAt"],
    )


def refresh_session_preview_best_effort(
    db: SessionDB,
    session_id: str,
    *,
    get_session_or_404: Callable[[SessionDB, str], dict[str, Any]],
    hidden_agent: HiddenAgent,
) -> None:
    try:
        generate_session_preview(
            db,
            session_id,
            get_session_or_404=get_session_or_404,
            hidden_agent=hidden_agent,
        )
    except Exception:
        # Preview summaries must never affect chat execution.
        return


def _stored_summary(session: dict[str, Any]) -> dict[str, Any] | None:
    value = session_model_config(session).get(SIDEBAR_SUMMARY_CONFIG_KEY)
    if not isinstance(value, dict):
        return None
    text = value.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    return {**value, "text": text.strip()}


def _summary_conversation_history(db: SessionDB, session: dict[str, Any]) -> list[dict[str, str]]:
    raw_messages = session_lineage_messages(db, session)
    history: list[dict[str, str]] = []
    total_chars = 0

    for message in reversed(raw_messages):
        role = str(message.get("role") or "")
        if role not in {"user", "assistant", "system"}:
            continue
        content = _plain_text(message.get("content"))
        if not content:
            continue
        if total_chars + len(content) > SUMMARY_INPUT_MAX_CHARS and history:
            break
        history.append({"role": role, "content": content})
        total_chars += len(content)

    history.reverse()
    return history


def _plain_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(part.strip() for part in parts if part.strip())
    return ""


def _clean_summary(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "")).strip().strip('"')
    if len(text) <= SUMMARY_MAX_CHARS:
        return text
    return text[: SUMMARY_MAX_CHARS - 1].rstrip() + "…"


def _iso_from_epoch(value: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
