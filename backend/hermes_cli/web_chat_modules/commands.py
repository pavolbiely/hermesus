"""Slash-command helpers for the web chat API."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from fastapi import HTTPException, status

from .models import ExecuteCommandRequest, ExecuteCommandResponse, WebChatCommand, WebChatMessage, WebChatPart, WebChatWorkspaceChanges


def web_chat_commands() -> list[WebChatCommand]:
    return [
        WebChatCommand(
            id="help",
            name="/help",
            description="Show available slash commands.",
            usage="/help",
        ),
        WebChatCommand(
            id="status",
            name="/status",
            description="Show current chat, model, and workspace status.",
            usage="/status",
        ),
        WebChatCommand(
            id="changes",
            name="/changes",
            description="Show current workspace changes.",
            usage="/changes",
            requiresWorkspace=True,
        ),
        WebChatCommand(
            id="clear",
            name="/clear",
            description="Clear the current chat after confirmation.",
            usage="/clear",
            safety="confirmation_required",
            requiresSession=True,
        ),
    ]


def web_chat_command(command_id: str) -> WebChatCommand:
    normalized = command_id.removeprefix("/").strip().lower()
    for command in web_chat_commands():
        if command.id == normalized:
            return command
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Command not found")


def transient_assistant_message(text: str, *, iso_now: Callable[[], str]) -> WebChatMessage:
    return WebChatMessage(
        id=f"command-{uuid4().hex}",
        role="assistant",
        parts=[WebChatPart(type="text", text=text)],
        createdAt=iso_now(),
    )


def execute_help_command(*, iso_now: Callable[[], str]) -> ExecuteCommandResponse:
    lines = ["Available slash commands:"]
    for command in web_chat_commands():
        if command.safety == "blocked":
            continue
        suffix = " (requires confirmation)" if command.safety == "confirmation_required" else ""
        lines.append(f"- {command.name} — {command.description}{suffix}")
    return ExecuteCommandResponse(commandId="help", message=transient_assistant_message("\n".join(lines), iso_now=iso_now))


def execute_status_command(request: ExecuteCommandRequest, *, iso_now: Callable[[], str]) -> ExecuteCommandResponse:
    workspace = request.workspace or "No workspace selected"
    model = request.model or "Default model"
    reasoning = request.reasoningEffort or "Default reasoning"
    session = request.sessionId or "New chat"
    text = "\n".join([
        "Chat status:",
        f"- Session: {session}",
        f"- Workspace: {workspace}",
        f"- Model: {model}",
        f"- Reasoning: {reasoning}",
    ])
    return ExecuteCommandResponse(commandId="status", message=transient_assistant_message(text, iso_now=iso_now))


def execute_changes_command(
    request: ExecuteCommandRequest,
    *,
    iso_now: Callable[[], str],
    validate_workspace: Callable[[str | None], Path],
    workspace_changes: Callable[[str], WebChatWorkspaceChanges],
) -> ExecuteCommandResponse:
    if not request.workspace:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select a workspace before running /changes.")
    workspace = validate_workspace(request.workspace)
    changes = workspace_changes(str(workspace))
    return ExecuteCommandResponse(
        commandId="changes",
        message=transient_assistant_message("Workspace changes:", iso_now=iso_now),
        changes=changes,
    )


def execute_web_chat_command(
    request: ExecuteCommandRequest,
    *,
    iso_now: Callable[[], str],
    validate_workspace: Callable[[str | None], Path],
    workspace_changes: Callable[[str], WebChatWorkspaceChanges],
) -> ExecuteCommandResponse:
    command = web_chat_command(request.command.split()[0])
    if command.safety == "blocked":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Command is blocked.")
    if command.safety == "confirmation_required":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This command requires confirmation.")
    if command.id == "help":
        return execute_help_command(iso_now=iso_now)
    if command.id == "status":
        return execute_status_command(request, iso_now=iso_now)
    if command.id == "changes":
        return execute_changes_command(
            request,
            iso_now=iso_now,
            validate_workspace=validate_workspace,
            workspace_changes=workspace_changes,
        )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Command not found")


def message_text(message: WebChatMessage) -> str:
    return "\n\n".join(part.text for part in message.parts if part.type == "text" and part.text)


def persist_command_exchange(
    request: ExecuteCommandRequest,
    response: ExecuteCommandResponse,
    *,
    db_factory: Callable[[], Any],
    get_session_or_404: Callable[[Any, str], Any],
    title_from_message: Callable[[str], str],
    validate_workspace: Callable[[str | None], Path],
    record_session_git_changes: Callable[..., None],
    git_status_porcelain: Callable[[str], str | None],
    serialize_message: Callable[[Any], WebChatMessage],
    web_chat_source: str,
) -> ExecuteCommandResponse:
    if not response.message:
        return response

    db = db_factory()
    session_id = request.sessionId or uuid4().hex
    if request.sessionId:
        get_session_or_404(db, session_id)
    else:
        model_config = {"workspace": request.workspace} if request.workspace else None
        db.create_session(session_id, source=web_chat_source, model=request.model, model_config=model_config)
        db.set_session_title(session_id, title_from_message(request.command.strip()))

    db.append_message(session_id, "user", request.command.strip())
    assistant_message_id = db.append_message(session_id, "assistant", message_text(response.message))

    if response.changes and response.changes.files and request.workspace:
        workspace = str(validate_workspace(request.workspace))
        record_session_git_changes(
            db,
            session_id=session_id,
            run_id=None,
            message_id=assistant_message_id,
            workspace=workspace,
            baseline_status=None,
            final_status=git_status_porcelain(workspace) or "",
            changes=response.changes,
        )

    messages = db.get_messages(session_id)
    persisted = next((message for message in messages if message.get("id") == assistant_message_id), None)
    if persisted:
        response.message = serialize_message(persisted)
    response.sessionId = session_id
    return response
