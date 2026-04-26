"""Session serialization helpers for the web chat API."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from hermes_state import SessionDB

from .attachments import attachment_with_runtime_state
from .models import WebChatAttachment, WebChatMessage, WebChatPart, WebChatPrompt, WebChatSession, WebChatWorkspaceChanges


def iso_from_epoch(value: Any) -> str:
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        timestamp = 0.0
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def parse_jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    text = value.strip()
    if not text or text[0] not in "[{":
        return value

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def session_model_config(session: dict[str, Any] | None) -> dict[str, Any]:
    if not session:
        return {}
    raw = session.get("model_config")
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def session_workspace(session: dict[str, Any] | None) -> str | None:
    config = session_model_config(session)
    value = config.get("workspace")
    return value.strip() if isinstance(value, str) and value.strip() else None


def session_reasoning_effort(session: dict[str, Any] | None) -> str | None:
    config = session_model_config(session)
    value = config.get("reasoningEffort") or config.get("reasoning_effort")
    if isinstance(value, str) and value.strip():
        return value.strip().lower()

    reasoning_config = config.get("reasoning_config")
    if isinstance(reasoning_config, dict):
        if reasoning_config.get("enabled") is False:
            return "none"
        effort = reasoning_config.get("effort")
        if isinstance(effort, str) and effort.strip():
            return effort.strip().lower()
    return None


def serialize_session(session: dict[str, Any]) -> WebChatSession:
    created_at = iso_from_epoch(session.get("started_at"))
    updated_at = iso_from_epoch(session.get("last_active") or session.get("started_at"))
    return WebChatSession(
        id=session["id"],
        title=session.get("title") or session.get("preview") or "New chat",
        preview=session.get("preview") or "",
        source=session.get("source"),
        model=session.get("model"),
        reasoningEffort=session_reasoning_effort(session),
        workspace=session_workspace(session),
        messageCount=session.get("message_count", 0),
        createdAt=created_at,
        updatedAt=updated_at,
    )


def message_attachments(message: dict[str, Any]) -> list[WebChatAttachment]:
    items = parse_jsonish(message.get("codex_message_items"))
    if not isinstance(items, list):
        return []

    attachments: list[WebChatAttachment] = []
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "web_chat_attachment":
            continue
        metadata = item.get("attachment")
        if not isinstance(metadata, dict):
            continue
        try:
            attachments.append(attachment_with_runtime_state(WebChatAttachment(**metadata)))
        except Exception:
            continue
    return attachments


def message_prompts(message: dict[str, Any]) -> list[WebChatPrompt]:
    items = parse_jsonish(message.get("codex_message_items"))
    if not isinstance(items, list):
        return []

    prompts: list[WebChatPrompt] = []
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "web_chat_prompt":
            continue
        metadata = item.get("prompt")
        if not isinstance(metadata, dict):
            continue
        try:
            prompts.append(WebChatPrompt(**metadata))
        except Exception:
            continue
    return prompts


def message_steers(message: dict[str, Any]) -> list[str]:
    items = parse_jsonish(message.get("codex_message_items"))
    if not isinstance(items, list):
        return []

    steers: list[str] = []
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "web_chat_steer":
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            steers.append(text)
    return steers


def message_parts(message: dict[str, Any]) -> list[WebChatPart]:
    parts: list[WebChatPart] = []
    attachments = message_attachments(message)
    if attachments:
        parts.append(WebChatPart(type="media", attachments=attachments))
    for prompt in message_prompts(message):
        parts.append(WebChatPart(type="interactive_prompt", prompt=prompt))
    for steer in message_steers(message):
        parts.append(WebChatPart(type="steer", text=steer))
    if message.get("reasoning") or message.get("reasoning_content"):
        parts.append(WebChatPart(type="reasoning", text=message.get("reasoning") or message.get("reasoning_content")))
    if message.get("content") and message.get("role") != "tool":
        parts.append(WebChatPart(type="text", text=message["content"]))
    if message.get("role") == "tool":
        parts.append(WebChatPart(type="tool", name=message.get("tool_name"), output=parse_jsonish(message.get("content"))))
    elif message.get("tool_name") or message.get("tool_calls"):
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            for tool_call in tool_calls:
                parts.append(WebChatPart(type="tool", name=tool_call_name(tool_call) or message.get("tool_name"), input=tool_call))
        else:
            parts.append(WebChatPart(type="tool", name=message.get("tool_name"), input=tool_calls))
    return parts


def serialize_message(message: dict[str, Any]) -> WebChatMessage:
    return WebChatMessage(
        id=str(message["id"]),
        role=message.get("role"),
        parts=message_parts(message),
        createdAt=iso_from_epoch(message.get("timestamp")),
        reasoning=message.get("reasoning") or message.get("reasoning_content"),
        toolName=message.get("tool_name"),
        toolCalls=message.get("tool_calls"),
    )


def tool_call_name(tool_call: Any) -> str | None:
    if not isinstance(tool_call, dict):
        return None

    function = tool_call.get("function")
    if isinstance(function, dict) and isinstance(function.get("name"), str):
        return function["name"]
    if isinstance(tool_call.get("name"), str):
        return tool_call["name"]
    return None


def tool_call_id(tool_call: Any) -> str | None:
    if not isinstance(tool_call, dict):
        return None

    value = tool_call.get("id") or tool_call.get("tool_call_id")
    return str(value) if value else None


def attach_tool_output(messages: list[WebChatMessage], tool_message: dict[str, Any]) -> bool:
    output = parse_jsonish(tool_message.get("content"))
    tool_call_id_value = str(tool_message.get("tool_call_id") or "")
    tool_name = tool_message.get("tool_name")

    for message in reversed(messages):
        if message.role != "assistant":
            continue

        fallback_part: WebChatPart | None = None
        for part in message.parts:
            if part.type != "tool" or part.output is not None:
                continue

            if not fallback_part:
                fallback_part = part

            if tool_call_id_value and tool_call_id(part.input) == tool_call_id_value:
                part.output = output
                if tool_name and not part.name:
                    part.name = tool_name
                return True

        if fallback_part:
            fallback_part.output = output
            if tool_name and not fallback_part.name:
                fallback_part.name = tool_name
            return True

    return False


def serialize_messages(
    messages: list[dict[str, Any]],
    *,
    changes_by_message: dict[str, WebChatWorkspaceChanges] | None = None,
) -> list[WebChatMessage]:
    serialized: list[WebChatMessage] = []
    for message in messages:
        if message.get("role") == "tool" and attach_tool_output(serialized, message):
            continue
        web_message = serialize_message(message)
        changes = (changes_by_message or {}).get(str(message.get("id")))
        if changes and changes.files:
            web_message.parts.append(WebChatPart(type="changes", changes=changes.model_dump()))
        serialized.append(web_message)
    return serialized


def get_session_or_404(db: SessionDB, session_id: str) -> dict[str, Any]:
    session = db._get_session_rich_row(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session
