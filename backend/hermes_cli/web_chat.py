"""Native web chat API for the Hermes dashboard.

This module exposes JSON/SSE endpoints for a first-class web chat UI. It keeps
``SessionDB`` as the source of truth and intentionally does not use the legacy
xterm/PTY dashboard chat transport.
"""

from __future__ import annotations

import json
import queue
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from hermes_state import SessionDB

router = APIRouter(prefix="/api/web-chat", tags=["web-chat"])

WEB_CHAT_SOURCE = "web-chat"
MAX_SESSION_LIMIT = 100
MAX_ATTACHMENTS_PER_REQUEST = 8
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
MAX_PATCH_BYTES_PER_FILE = 96 * 1024
MAX_PATCH_BYTES_PER_RUN = 512 * 1024
RunExecutor = Callable[["RunContext", Callable[[dict[str, Any]], None]], str]
_KNOWN_ATTACHMENT_ROOTS: set[Path] = set()
_PROJECT_SETTINGS_LOCK = threading.Lock()


class WebChatAttachment(BaseModel):
    id: str
    name: str
    mediaType: str
    size: int
    path: str
    workspace: str | None = None
    relativePath: str | None = None
    url: str | None = None
    exists: bool = True


class WebChatPart(BaseModel):
    type: Literal["text", "reasoning", "tool", "media", "approval", "changes"]
    text: str | None = None
    name: str | None = None
    status: str | None = None
    input: Any | None = None
    output: Any | None = None
    url: str | None = None
    mediaType: str | None = None
    approvalId: str | None = None
    changes: Any | None = None
    attachments: list[WebChatAttachment] | None = None


class WebChatMessage(BaseModel):
    id: str
    role: Literal["user", "assistant", "system", "tool"]
    parts: list[WebChatPart]
    createdAt: str
    reasoning: str | None = None
    toolName: str | None = None
    toolCalls: Any | None = None


class WebChatSession(BaseModel):
    id: str
    title: str | None
    preview: str
    source: str | None
    model: str | None
    reasoningEffort: str | None = None
    workspace: str | None = None
    messageCount: int
    createdAt: str
    updatedAt: str


class WebChatModelCapability(BaseModel):
    id: str
    label: str
    reasoningEfforts: list[str]
    defaultReasoningEffort: str | None = None


class WebChatCapabilitiesResponse(BaseModel):
    provider: str
    defaultModel: str | None
    models: list[WebChatModelCapability]


class WebChatFileChange(BaseModel):
    path: str
    status: str
    additions: int
    deletions: int


class WebChatWorkspaceChanges(BaseModel):
    files: list[WebChatFileChange]
    totalFiles: int
    totalAdditions: int
    totalDeletions: int
    workspace: str | None = None
    runId: str | None = None
    capturedAt: str | None = None
    patch: dict[str, Any] | None = None
    patchTruncated: bool | None = None


class WebChatProfile(BaseModel):
    id: str
    label: str
    path: str
    active: bool = False


class WebChatProfilesResponse(BaseModel):
    profiles: list[WebChatProfile]
    activeProfile: str


class SwitchProfileRequest(BaseModel):
    profile: str = Field(min_length=1, max_length=64)
    restart: bool = True


class SwitchProfileResponse(BaseModel):
    profiles: list[WebChatProfile]
    activeProfile: str
    restarting: bool = False


class WebChatWorkspace(BaseModel):
    id: str
    label: str
    path: str
    active: bool = False


class WebChatWorkspacesResponse(BaseModel):
    workspaces: list[WebChatWorkspace]
    activeWorkspace: str | None = None


class WebChatWorkspaceResponse(BaseModel):
    workspace: WebChatWorkspace


class SaveWorkspaceRequest(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    path: str = Field(min_length=1, max_length=4096)


class DirectorySuggestionsResponse(BaseModel):
    suggestions: list[str]


class UploadAttachmentsResponse(BaseModel):
    attachments: list[WebChatAttachment]


class SessionListResponse(BaseModel):
    sessions: list[WebChatSession]


class SessionDetailResponse(BaseModel):
    session: WebChatSession
    messages: list[WebChatMessage]


class CreateSessionRequest(BaseModel):
    message: str = Field(min_length=1, max_length=65536)


class RenameSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class EditMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=65536)


class DeleteSessionResponse(BaseModel):
    ok: bool


class StartRunRequest(BaseModel):
    sessionId: str | None = None
    input: str = Field(min_length=1, max_length=65536)
    workspace: str | None = None
    profile: str | None = None
    attachments: list[str] | None = None
    editedMessageId: str | None = None
    model: str | None = None
    reasoningEffort: str | None = None
    provider: str | None = None
    enabledToolsets: list[str] | None = None


class StartRunResponse(BaseModel):
    sessionId: str
    runId: str


class StopRunResponse(BaseModel):
    runId: str
    stopped: bool


@dataclass
class RunContext:
    run_id: str
    session_id: str
    input: str
    workspace: str | None = None
    profile: str | None = None
    attachments: list[str] | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    provider: str | None = None
    enabled_toolsets: list[str] | None = None
    baseline_git_status: str | None = None
    stop_requested: threading.Event = field(default_factory=threading.Event)


@dataclass
class ActiveRun:
    context: RunContext
    events: "queue.Queue[dict[str, Any] | None]" = field(default_factory=queue.Queue)
    thread: threading.Thread | None = None
    created_at: float = field(default_factory=time.time)


class RunManager:
    def __init__(self, executor: RunExecutor | None = None):
        self._runs: dict[str, ActiveRun] = {}
        self._lock = threading.Lock()
        self._executor = executor or self._not_configured_executor

    def start(self, request: StartRunRequest) -> StartRunResponse:
        db = _db()
        session_id = request.sessionId or uuid4().hex
        session = None
        if request.sessionId:
            session = db.get_session(request.sessionId)
            if not session:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
            db.reopen_session(request.sessionId)
        else:
            session = None

        effective_model = _resolve_requested_model(request.model, session=session)
        effective_reasoning_effort = _resolve_requested_reasoning_effort(
            effective_model,
            request.reasoningEffort,
            session=session,
        )
        provided_fields = getattr(request, "model_fields_set", None)
        if provided_fields is None:
            provided_fields = getattr(request, "__fields_set__", set())
        workspace_provided = "workspace" in provided_fields
        workspace = _validate_workspace(request.workspace) if workspace_provided else _validate_workspace(_session_workspace(session))
        workspace_path = str(workspace) if workspace else None
        profile = _validate_profile(request.profile)
        attachments = _resolve_attachments(request.attachments, workspace_path)
        if request.editedMessageId:
            if not request.sessionId:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Edited message requires an existing chat.")
            _validate_edited_message_continuation(db, session_id, request.editedMessageId)
        if attachments and not workspace_path:
            attachment_workspaces = {attachment.workspace for attachment in attachments if attachment.workspace}
            if len(attachment_workspaces) == 1:
                workspace = _validate_workspace(next(iter(attachment_workspaces)))
                workspace_path = str(workspace) if workspace else None
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select a workspace before sending attachments.")
        effective_input = _input_with_attachment_context(request.input, attachments)

        model_config_updates = {"reasoningEffort": effective_reasoning_effort}
        if workspace_provided or workspace_path:
            model_config_updates["workspace"] = workspace_path

        if request.sessionId:
            db.update_session_model_settings(
                session_id,
                model=effective_model,
                model_config_updates=model_config_updates,
            )
        else:
            db.create_session(
                session_id,
                source=WEB_CHAT_SOURCE,
                model=effective_model,
                model_config=model_config_updates,
            )
            _set_session_title_safely(db, session_id, _title_from_message(request.input))

        if not request.editedMessageId:
            attachment_items = [
                {"type": "web_chat_attachment", "attachment": attachment.model_dump()}
                for attachment in attachments
            ]
            db.append_message(
                session_id,
                "user",
                request.input,
                codex_message_items=attachment_items or None,
            )

        baseline_git_status = _git_status_porcelain(workspace_path) if workspace_path else None

        run_id = uuid4().hex
        context = RunContext(
            run_id=run_id,
            session_id=session_id,
            input=effective_input,
            workspace=str(workspace) if workspace else None,
            profile=profile,
            attachments=[attachment.id for attachment in attachments] or None,
            model=effective_model,
            reasoning_effort=effective_reasoning_effort,
            provider=request.provider,
            enabled_toolsets=request.enabledToolsets,
            baseline_git_status=baseline_git_status,
        )
        active = ActiveRun(context=context)
        active.thread = threading.Thread(target=self._run, args=(active,), daemon=True)
        with self._lock:
            self._runs[run_id] = active
        active.thread.start()
        return StartRunResponse(sessionId=session_id, runId=run_id)

    def events(self, run_id: str):
        active = self._get(run_id)
        while True:
            event = active.events.get()
            if event is None:
                break
            yield f"event: {event['type']}\n"
            yield f"data: {json.dumps(event, separators=(',', ':'))}\n\n"

    def stop(self, run_id: str) -> StopRunResponse:
        active = self._get(run_id)
        active.context.stop_requested.set()
        active.events.put({"type": "run.stopping", "runId": run_id})
        return StopRunResponse(runId=run_id, stopped=True)

    def has_running_runs(self) -> bool:
        with self._lock:
            return any(active.thread and active.thread.is_alive() for active in self._runs.values())

    def _get(self, run_id: str) -> ActiveRun:
        with self._lock:
            active = self._runs.get(run_id)
        if not active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
        return active

    def _emit(self, active: ActiveRun, event: dict[str, Any]) -> None:
        active.events.put({"runId": active.context.run_id, "sessionId": active.context.session_id, **event})

    def _run(self, active: ActiveRun) -> None:
        self._emit(active, {"type": "run.started"})
        assistant_message_id: int | None = None
        try:
            final_text = self._executor(active.context, lambda event: self._emit(active, event))
            if active.context.stop_requested.is_set():
                self._emit(active, {"type": "run.stopped"})
                return
            if final_text:
                assistant_message_id = _db().append_message(active.context.session_id, "assistant", final_text)
                _persist_run_workspace_changes(active.context, assistant_message_id)
                self._emit(active, {"type": "message.completed", "content": final_text})
            self._emit(active, {"type": "run.completed"})
        except Exception as exc:
            self._emit(active, {"type": "run.failed", "error": str(exc)})
        finally:
            if assistant_message_id is None:
                _persist_run_workspace_changes(active.context, None)
            active.events.put(None)

    @staticmethod
    def _not_configured_executor(context: RunContext, emit: Callable[[dict[str, Any]], None]) -> str:
        return _agent_executor(context, emit)


def _agent_executor(context: RunContext, emit: Callable[[dict[str, Any]], None]) -> str:
    """Run a real Hermes Agent turn and stream text deltas to the web UI."""
    from hermes_constants import parse_reasoning_effort
    from hermes_cli.config import load_config
    from hermes_cli.runtime_provider import resolve_runtime_provider
    from run_agent import AIAgent

    cfg = load_config() or {}
    model_cfg = cfg.get("model") or {}
    agent_cfg = cfg.get("agent") or {}
    provider_routing = cfg.get("provider_routing") or {}

    runtime = resolve_runtime_provider(
        requested=context.provider or model_cfg.get("provider") or "auto",
        explicit_base_url=model_cfg.get("base_url"),
    )
    model = context.model or runtime.get("model") or model_cfg.get("default") or model_cfg.get("model") or ""
    api_key = runtime.get("api_key")
    base_url = runtime.get("base_url")
    reasoning_config = parse_reasoning_effort(context.reasoning_effort or "")
    if not api_key and base_url and "openrouter.ai" not in base_url:
        api_key = "no-key-required"

    def stream_delta(text: str) -> None:
        if text:
            emit({"type": "message.delta", "content": text})

    def reasoning_delta(text: str) -> None:
        if text:
            emit({"type": "reasoning.delta", "content": text})

    def tool_progress(kind: str, tool_name: str | None = None, preview: str | None = None, args: Any | None = None) -> None:
        if kind not in {"tool.started", "tool.completed"}:
            return

        emit({
            "type": kind,
            "name": tool_name or "Tool call",
            "preview": preview,
            "input": args,
        })

    agent = AIAgent(
        model=model,
        api_key=api_key,
        base_url=base_url,
        provider=runtime.get("provider"),
        api_mode=runtime.get("api_mode"),
        acp_command=runtime.get("command"),
        acp_args=runtime.get("args"),
        credential_pool=runtime.get("credential_pool"),
        max_iterations=int(agent_cfg.get("max_turns") or cfg.get("max_turns") or 90),
        enabled_toolsets=context.enabled_toolsets,
        quiet_mode=True,
        platform=WEB_CHAT_SOURCE,
        session_id=context.session_id,
        session_db=None,
        persist_session=False,
        fallback_model=cfg.get("fallback_providers") or cfg.get("fallback_model") or None,
        providers_allowed=provider_routing.get("only"),
        providers_ignored=provider_routing.get("ignore"),
        providers_order=provider_routing.get("order"),
        provider_sort=provider_routing.get("sort"),
        reasoning_config=reasoning_config,
        stream_delta_callback=stream_delta,
        reasoning_callback=reasoning_delta,
        tool_progress_callback=tool_progress,
    )

    prompt = context.input
    if context.workspace:
        prompt = (
            f"Workspace: {context.workspace}. Use tool workdir/path arguments for file and terminal operations in this workspace.\n\n"
            f"{prompt}"
        )

    result = agent.run_conversation(
        prompt,
        conversation_history=_conversation_history_for_agent(context.session_id),
        task_id=context.run_id,
    )
    return str(result.get("final_response") or "")


def _conversation_history_for_agent(session_id: str) -> list[dict[str, str]]:
    messages = _db().get_messages(session_id)
    if messages and messages[-1].get("role") == "user":
        messages = messages[:-1]

    history: list[dict[str, str]] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role in {"system", "user", "assistant"} and isinstance(content, str) and content:
            history.append({"role": role, "content": content})
    return history


run_manager = RunManager()


def _db() -> SessionDB:
    return SessionDB()


def _ensure_workspace_schema(db: SessionDB) -> None:
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


def _workspace_from_row(row: Any) -> WebChatWorkspace:
    return _workspace_from_mapping(row)


def _workspace_from_mapping(value: Any) -> WebChatWorkspace:
    return WebChatWorkspace(
        id=value["id"],
        label=value["label"],
        path=value["path"],
        active=False,
    )


def _normalize_workspace_path(path: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Directory does not exist")
    return candidate.resolve()


def _project_root() -> Path:
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


def _project_web_chat_settings_path() -> Path:
    return _project_root() / ".hermes" / "web-chat" / "settings.json"


def _empty_project_settings() -> dict[str, Any]:
    return {"version": 1, "workspaces": []}


def _read_legacy_db_workspaces(db: SessionDB | None = None) -> list[WebChatWorkspace]:
    db = db or _db()
    _ensure_workspace_schema(db)
    with db._lock:
        rows = db._conn.execute(
            "SELECT id, label, path FROM web_chat_workspaces ORDER BY label COLLATE NOCASE ASC, created_at ASC"
        ).fetchall()
    return [_workspace_from_row(row) for row in rows]


def _load_project_settings() -> dict[str, Any]:
    path = _project_web_chat_settings_path()
    if not path.exists():
        migrated = [
            {"id": workspace.id, "label": workspace.label, "path": workspace.path}
            for workspace in _read_legacy_db_workspaces()
        ]
        settings = {"version": 1, "workspaces": migrated}
        if migrated:
            _write_project_settings(settings)
        return settings

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid web chat settings file") from exc

    if not isinstance(data, dict):
        return _empty_project_settings()
    workspaces = data.get("workspaces")
    if not isinstance(workspaces, list):
        data["workspaces"] = []
    data.setdefault("version", 1)
    return data


def _write_project_settings(settings: dict[str, Any]) -> None:
    path = _project_web_chat_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(settings, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _workspace_entries(settings: dict[str, Any]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for item in settings.get("workspaces", []):
        if not isinstance(item, dict):
            continue
        try:
            entries.append({"id": str(item["id"]), "label": str(item["label"]), "path": str(item["path"])})
        except KeyError:
            continue
    return entries


def _list_managed_workspaces(db: SessionDB | None = None) -> list[WebChatWorkspace]:
    del db
    with _PROJECT_SETTINGS_LOCK:
        entries = _workspace_entries(_load_project_settings())
    return sorted(
        (_workspace_from_mapping(entry) for entry in entries),
        key=lambda workspace: (workspace.label.lower(), workspace.label, workspace.path),
    )


def _find_managed_workspace_by_path(path: Path, db: SessionDB | None = None) -> WebChatWorkspace | None:
    del db
    resolved = str(path.resolve())
    with _PROJECT_SETTINGS_LOCK:
        for entry in _workspace_entries(_load_project_settings()):
            if entry["path"] == resolved:
                return _workspace_from_mapping(entry)
    return None


def _get_managed_workspace(workspace_id: str, db: SessionDB | None = None) -> WebChatWorkspace:
    del db
    with _PROJECT_SETTINGS_LOCK:
        for entry in _workspace_entries(_load_project_settings()):
            if entry["id"] == workspace_id:
                return _workspace_from_mapping(entry)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")


def _create_managed_workspace(request: SaveWorkspaceRequest) -> WebChatWorkspace:
    path = str(_normalize_workspace_path(request.path))
    workspace_id = uuid4().hex
    label = request.label.strip()

    with _PROJECT_SETTINGS_LOCK:
        settings = _load_project_settings()
        entries = _workspace_entries(settings)
        if any(entry["path"] == path for entry in entries):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Workspace path already exists")
        workspace = {"id": workspace_id, "label": label, "path": path}
        settings["workspaces"] = [*entries, workspace]
        _write_project_settings(settings)

    return _workspace_from_mapping(workspace)


def _update_managed_workspace(workspace_id: str, request: SaveWorkspaceRequest) -> WebChatWorkspace:
    path = str(_normalize_workspace_path(request.path))
    label = request.label.strip()

    with _PROJECT_SETTINGS_LOCK:
        settings = _load_project_settings()
        entries = _workspace_entries(settings)
        existing = next((entry for entry in entries if entry["id"] == workspace_id), None)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
        if any(entry["id"] != workspace_id and entry["path"] == path for entry in entries):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Workspace path already exists")

        updated = {"id": workspace_id, "label": label, "path": path}
        settings["workspaces"] = [updated if entry["id"] == workspace_id else entry for entry in entries]
        _write_project_settings(settings)

    return _workspace_from_mapping(updated)


def _delete_managed_workspace(workspace_id: str) -> None:
    with _PROJECT_SETTINGS_LOCK:
        settings = _load_project_settings()
        entries = _workspace_entries(settings)
        if not any(entry["id"] == workspace_id for entry in entries):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
        settings["workspaces"] = [entry for entry in entries if entry["id"] != workspace_id]
        _write_project_settings(settings)


def _ensure_git_change_schema(db: SessionDB) -> None:
    def _do(conn):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS web_chat_git_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                run_id TEXT,
                message_id INTEGER,
                workspace TEXT NOT NULL,
                baseline_status TEXT,
                final_status TEXT NOT NULL,
                files_json TEXT NOT NULL,
                patch_json TEXT,
                patch_truncated INTEGER NOT NULL DEFAULT 0,
                total_files INTEGER NOT NULL DEFAULT 0,
                total_additions INTEGER NOT NULL DEFAULT 0,
                total_deletions INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_web_chat_git_changes_session ON web_chat_git_changes(session_id, created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_web_chat_git_changes_message ON web_chat_git_changes(message_id)"
        )

    db._execute_write(_do)


def _record_session_git_changes(
    db: SessionDB,
    *,
    session_id: str,
    run_id: str | None,
    message_id: int | None,
    workspace: str,
    baseline_status: str | None,
    final_status: str,
    changes: WebChatWorkspaceChanges,
) -> None:
    if not changes.files:
        return

    _ensure_git_change_schema(db)
    files_json = json.dumps([file.model_dump() for file in changes.files], separators=(",", ":"))
    patch_json = json.dumps(changes.patch, separators=(",", ":")) if changes.patch else None

    def _do(conn):
        conn.execute(
            """
            INSERT INTO web_chat_git_changes (
                session_id, run_id, message_id, workspace, baseline_status, final_status,
                files_json, patch_json, patch_truncated, total_files, total_additions,
                total_deletions, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                run_id,
                message_id,
                workspace,
                baseline_status,
                final_status,
                files_json,
                patch_json,
                1 if changes.patchTruncated else 0,
                changes.totalFiles,
                changes.totalAdditions,
                changes.totalDeletions,
                time.time(),
            ),
        )

    db._execute_write(_do)


def _session_git_changes_by_message(db: SessionDB, session_id: str) -> dict[str, WebChatWorkspaceChanges]:
    _ensure_git_change_schema(db)
    with db._lock:
        rows = db._conn.execute(
            """
            SELECT * FROM web_chat_git_changes
            WHERE session_id = ? AND message_id IS NOT NULL
            ORDER BY created_at ASC, id ASC
            """,
            (session_id,),
        ).fetchall()

    changes_by_message: dict[str, WebChatWorkspaceChanges] = {}
    for row in rows:
        try:
            files = [WebChatFileChange(**item) for item in json.loads(row["files_json"] or "[]")]
            patch = json.loads(row["patch_json"]) if row["patch_json"] else None
        except Exception:
            continue
        changes_by_message[str(row["message_id"])] = WebChatWorkspaceChanges(
            files=files,
            totalFiles=row["total_files"],
            totalAdditions=row["total_additions"],
            totalDeletions=row["total_deletions"],
            workspace=row["workspace"],
            runId=row["run_id"],
            capturedAt=_iso_from_epoch(row["created_at"]),
            patch=patch,
            patchTruncated=bool(row["patch_truncated"]),
        )
    return changes_by_message


def _copy_session_git_changes(
    db: SessionDB,
    *,
    source_session_id: str,
    target_session_id: str,
    message_id_map: dict[int, int],
) -> None:
    _ensure_git_change_schema(db)
    with db._lock:
        rows = db._conn.execute(
            "SELECT * FROM web_chat_git_changes WHERE session_id = ? ORDER BY created_at ASC, id ASC",
            (source_session_id,),
        ).fetchall()

    for row in rows:
        source_message_id = row["message_id"]
        target_message_id = message_id_map.get(source_message_id) if source_message_id is not None else None
        files = [WebChatFileChange(**item) for item in json.loads(row["files_json"] or "[]")]
        _record_session_git_changes(
            db,
            session_id=target_session_id,
            run_id=row["run_id"],
            message_id=target_message_id,
            workspace=row["workspace"],
            baseline_status=row["baseline_status"],
            final_status=row["final_status"],
            changes=WebChatWorkspaceChanges(
                files=files,
                totalFiles=row["total_files"],
                totalAdditions=row["total_additions"],
                totalDeletions=row["total_deletions"],
                workspace=row["workspace"],
                runId=row["run_id"],
                patch=json.loads(row["patch_json"]) if row["patch_json"] else None,
                patchTruncated=bool(row["patch_truncated"]),
            ),
        )


def _delete_session_git_changes(db: SessionDB, session_id: str) -> None:
    _ensure_git_change_schema(db)

    def _do(conn):
        conn.execute("DELETE FROM web_chat_git_changes WHERE session_id = ?", (session_id,))

    db._execute_write(_do)


def _delete_session_git_changes_after_message(db: SessionDB, session_id: str, message_id: int) -> None:
    _ensure_git_change_schema(db)

    def _do(conn):
        conn.execute(
            "DELETE FROM web_chat_git_changes WHERE session_id = ? AND message_id > ?",
            (session_id, message_id),
        )

    db._execute_write(_do)


def _edit_user_message(db: SessionDB, session_id: str, message_id: str, content: str) -> None:
    try:
        numeric_message_id = int(message_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found") from exc

    def _do(conn):
        row = conn.execute(
            "SELECT * FROM messages WHERE id = ? AND session_id = ?",
            (numeric_message_id, session_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
        if row["role"] != "user":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only user messages can be edited.")

        conn.execute(
            "UPDATE messages SET content = ? WHERE id = ? AND session_id = ?",
            (content, numeric_message_id, session_id),
        )
        conn.execute(
            "DELETE FROM messages WHERE session_id = ? AND id > ?",
            (session_id, numeric_message_id),
        )
        counts = conn.execute(
            """
            SELECT
                COUNT(*) AS message_count,
                SUM(CASE WHEN role = 'tool' OR tool_calls IS NOT NULL THEN 1 ELSE 0 END) AS tool_call_count
            FROM messages
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        conn.execute(
            "UPDATE sessions SET message_count = ?, tool_call_count = ? WHERE id = ?",
            (counts["message_count"] or 0, counts["tool_call_count"] or 0, session_id),
        )

    db._execute_write(_do)
    _delete_session_git_changes_after_message(db, session_id, numeric_message_id)


def _validate_edited_message_continuation(db: SessionDB, session_id: str, message_id: str) -> None:
    try:
        numeric_message_id = int(message_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found") from exc

    messages = db.get_messages(session_id)
    if not messages:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    latest = messages[-1]
    if latest.get("id") != numeric_message_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Edited message must be the latest message in the chat.")
    if latest.get("role") != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only user messages can be edited.")


def _persist_run_workspace_changes(context: RunContext, message_id: int | None) -> None:
    if not context.workspace:
        return
    final_status = _git_status_porcelain(context.workspace)
    if final_status is None or final_status == (context.baseline_git_status or ""):
        return

    changes = _workspace_changes_since(context.workspace, context.baseline_git_status or "", context.run_id)
    if not changes.files:
        return
    _record_session_git_changes(
        _db(),
        session_id=context.session_id,
        run_id=context.run_id,
        message_id=message_id,
        workspace=context.workspace,
        baseline_status=context.baseline_git_status or "",
        final_status=final_status,
        changes=changes,
    )


def _git_status_porcelain(workspace: str | None) -> str | None:
    root = _workspace_root(workspace)
    if not root:
        return None
    try:
        return subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except Exception:
        return None


def _status_paths(status_text: str) -> set[str]:
    paths: set[str] = set()
    for line in status_text.splitlines():
        if not line:
            continue
        value = line[3:] if len(line) > 3 else line
        if " -> " in value:
            value = value.rsplit(" -> ", 1)[-1]
        if value:
            paths.add(value)
    return paths


def _workspace_changes_since(workspace: str, baseline_status: str, run_id: str | None) -> WebChatWorkspaceChanges:
    root = _workspace_root(workspace)
    if not root:
        return WebChatWorkspaceChanges(files=[], totalFiles=0, totalAdditions=0, totalDeletions=0)

    baseline_paths = _status_paths(baseline_status)
    current = _workspace_changes(str(root))
    files = sorted(
        [file for file in current.files if file.path not in baseline_paths],
        key=lambda file: file.path,
    )
    patch, patch_truncated = _workspace_patch(root, files)
    return WebChatWorkspaceChanges(
        files=files,
        totalFiles=len(files),
        totalAdditions=sum(file.additions for file in files),
        totalDeletions=sum(file.deletions for file in files),
        workspace=str(root),
        runId=run_id,
        patch=patch,
        patchTruncated=patch_truncated,
    )


def _workspace_patch(root: Path, files: list[WebChatFileChange]) -> tuple[dict[str, Any] | None, bool]:
    patch_files: list[dict[str, Any]] = []
    total_bytes = 0
    truncated_any = False

    for file in files:
        patch_text = _file_patch(root, file)
        truncated = False
        if patch_text is not None:
            encoded = patch_text.encode("utf-8", errors="ignore")
            if len(encoded) > MAX_PATCH_BYTES_PER_FILE:
                patch_text = encoded[:MAX_PATCH_BYTES_PER_FILE].decode("utf-8", errors="ignore")
                truncated = True
            total_bytes += len(patch_text.encode("utf-8", errors="ignore"))
            if total_bytes > MAX_PATCH_BYTES_PER_RUN:
                patch_text = None
                truncated = True
        truncated_any = truncated_any or truncated
        patch_files.append({
            "path": file.path,
            "status": file.status,
            "patch": patch_text,
            "truncated": truncated,
        })

    return ({"files": patch_files} if patch_files else None), truncated_any


def _file_patch(root: Path, file: WebChatFileChange) -> str | None:
    if file.status == "created" and not _is_git_tracked(root, file.path):
        return _untracked_file_patch(root, file.path)

    try:
        result = subprocess.run(
            ["git", "-C", str(root), "diff", "--", file.path],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None
    return result.stdout or None


def _is_git_tracked(root: Path, path: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(root), "ls-files", "--error-unmatch", path],
        capture_output=True,
        text=True,
        timeout=10,
    ).returncode == 0


def _untracked_file_patch(root: Path, path: str) -> str | None:
    file_path = root / path
    try:
        data = file_path.read_bytes()
    except Exception:
        return None
    if b"\0" in data:
        return None
    text = data.decode("utf-8", errors="ignore")
    lines = text.splitlines()
    header = [
        "diff --git a/{path} b/{path}".format(path=path),
        "new file mode 100644",
        "--- /dev/null",
        f"+++ b/{path}",
        f"@@ -0,0 +1,{len(lines)} @@",
    ]
    body = [f"+{line}" for line in lines]
    return "\n".join(header + body) + "\n"


def _profile_dependencies():
    from hermes_cli.profiles import (
        get_active_profile,
        list_profiles,
        profile_exists,
        resolve_profile_env,
        set_active_profile,
        validate_profile_name,
    )

    return get_active_profile, list_profiles, profile_exists, resolve_profile_env, set_active_profile, validate_profile_name


def _list_web_chat_profiles() -> WebChatProfilesResponse:
    try:
        get_active_profile, list_profiles, _, _, _, _ = _profile_dependencies()
        active = get_active_profile()
        profiles = [
            WebChatProfile(
                id=profile.name,
                label=profile.name,
                path=str(profile.path),
                active=profile.name == active,
            )
            for profile in list_profiles()
        ]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not load Hermes profiles: {exc}",
        ) from exc

    return WebChatProfilesResponse(profiles=profiles, activeProfile=active)


def _restart_backend_soon() -> None:
    def restart() -> None:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)

    threading.Timer(0.35, restart).start()


def _switch_web_chat_profile(payload: SwitchProfileRequest) -> SwitchProfileResponse:
    requested = payload.profile.strip()
    try:
        get_active_profile, list_profiles, profile_exists, resolve_profile_env, set_active_profile, validate_profile_name = _profile_dependencies()
        validate_profile_name(requested)
        if not profile_exists(requested):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Hermes profile does not exist")
        resolve_profile_env(requested)
        current = get_active_profile()
        profiles = list_profiles()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Could not switch Hermes profile: {exc}") from exc

    if requested != current and run_manager.has_running_runs():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Wait for running chats to finish before switching profiles.")

    if requested != current:
        try:
            set_active_profile(requested)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Could not switch Hermes profile: {exc}") from exc

        if payload.restart:
            _restart_backend_soon()

    return SwitchProfileResponse(
        profiles=[
            WebChatProfile(
                id=profile.name,
                label=profile.name,
                path=str(profile.path),
                active=profile.name == requested,
            )
            for profile in profiles
        ],
        activeProfile=requested,
        restarting=payload.restart and requested != current,
    )


def _validate_profile(profile: str | None) -> str | None:
    requested = str(profile or "").strip()
    if not requested:
        return None

    try:
        get_active_profile, _, profile_exists, _, _, validate_profile_name = _profile_dependencies()
        validate_profile_name(requested)
        if not profile_exists(requested):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Hermes profile does not exist")
        active = get_active_profile()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Could not validate Hermes profile: {exc}") from exc

    if requested != active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Switching Hermes profile requires a backend restart in this prototype. Current profile: {active}.",
        )
    return requested


def _workspace_label(path: Path) -> str:
    return path.name or str(path)


def _validate_workspace(workspace: str | None) -> Path | None:
    if not workspace:
        return None
    candidate = Path(workspace).expanduser()
    if not candidate.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Directory does not exist")

    resolved = candidate.resolve()
    if _find_managed_workspace_by_path(resolved):
        return resolved

    root = _workspace_root(str(candidate))
    if root:
        return root.resolve()

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Directory is not a managed or git workspace")


def _list_web_chat_workspaces() -> WebChatWorkspacesResponse:
    return WebChatWorkspacesResponse(workspaces=_list_managed_workspaces(), activeWorkspace=None)


def _directory_suggestions(prefix: str, *, limit: int = 300) -> list[str]:
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


def _default_workspace() -> Path | None:
    active = _list_web_chat_workspaces().activeWorkspace
    return Path(active) if active else None


def _attachment_root(workspace: str | None = None) -> Path:
    root = _validate_workspace(workspace)
    if not root:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select a workspace before attaching files.")
    return root / ".hermes" / "attachments"


def _is_safe_attachment_id(attachment_id: str) -> bool:
    return bool(attachment_id) and attachment_id.isalnum()


def _safe_filename(filename: str | None) -> str:
    name = Path(filename or "attachment").name.strip()
    cleaned = "".join(char if char.isalnum() or char in {" ", ".", "-", "_"} else "-" for char in name)
    return cleaned.strip(" .") or "attachment"


def _unique_attachment_path(root: Path, filename: str) -> Path:
    candidate = root / filename
    stem = candidate.stem or "attachment"
    suffix = candidate.suffix
    index = 2
    while candidate.exists() or candidate.with_name(f"{candidate.name}.web-chat.json").exists():
        candidate = root / f"{stem} {index}{suffix}"
        index += 1
    return candidate


def _attachment_meta_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.web-chat.json")


def _attachment_url(attachment_id: str) -> str:
    return f"/api/web-chat/attachments/{attachment_id}/content"


def _attachment_with_runtime_state(attachment: WebChatAttachment) -> WebChatAttachment:
    exists = Path(attachment.path).is_file()
    return attachment.model_copy(update={"url": _attachment_url(attachment.id), "exists": exists})


def _attachment_metadata_roots(workspace: str | None = None) -> list[Path]:
    roots = set(_KNOWN_ATTACHMENT_ROOTS)
    if workspace:
        roots.add(_attachment_root(workspace))
    try:
        for item in _list_web_chat_workspaces().workspaces:
            roots.add(Path(item.path) / ".hermes" / "attachments")
    except Exception:
        pass
    return sorted(roots, key=str)


def _load_attachment(attachment_id: str, workspace: str | None = None) -> WebChatAttachment:
    if not _is_safe_attachment_id(attachment_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    for root in _attachment_metadata_roots(workspace):
        if not root.is_dir():
            continue
        for meta_path in root.glob("*.web-chat.json"):
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if metadata.get("id") == attachment_id:
                return _attachment_with_runtime_state(WebChatAttachment(**metadata))

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")


def _resolve_attachments(ids: list[str] | None, workspace: str | None = None) -> list[WebChatAttachment]:
    if not ids:
        return []

    attachments: list[WebChatAttachment] = []
    for attachment_id in ids:
        try:
            attachment = _load_attachment(attachment_id, workspace)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment no longer exists. Upload it again.") from exc
            raise
        if not attachment.exists:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment file no longer exists. Upload it again.")
        if workspace and attachment.workspace and Path(attachment.workspace).resolve() != Path(workspace).resolve():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment belongs to a different workspace. Upload it again.")
        attachments.append(attachment)
    return attachments


def _input_with_attachment_context(input_text: str, attachments: list[WebChatAttachment]) -> str:
    if not attachments:
        return input_text
    lines = ["Attached files:"]
    lines.extend(
        (
            f"- {attachment.name} (path: {attachment.path}, relative path: {attachment.relativePath}, "
            f"media type: {attachment.mediaType}, size: {attachment.size} bytes)"
        )
        for attachment in attachments
    )
    lines.append("Use file/document tools if you need to inspect them.")
    return f"{input_text}\n\n" + "\n".join(lines)


async def _store_upload(file: UploadFile, workspace: str | None = None) -> WebChatAttachment:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment is empty")
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is too large. Maximum size is 25 MB.")

    root = _attachment_root(workspace)
    project = root.parent.parent
    root.mkdir(parents=True, exist_ok=True)
    _KNOWN_ATTACHMENT_ROOTS.add(root)

    filename = _safe_filename(file.filename)
    path = _unique_attachment_path(root, filename)
    path.write_bytes(data)

    attachment_id = uuid4().hex
    relative_path = path.relative_to(project)
    attachment = WebChatAttachment(
        id=attachment_id,
        name=path.name,
        mediaType=file.content_type or "application/octet-stream",
        size=len(data),
        path=str(path),
        workspace=str(project),
        relativePath=str(relative_path),
        url=_attachment_url(attachment_id),
        exists=True,
    )
    _attachment_meta_path(path).write_text(attachment.model_dump_json(), encoding="utf-8")
    return attachment

def _iso_from_epoch(value: Any) -> str:
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        timestamp = 0.0
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _title_from_message(message: str) -> str:
    text = " ".join(message.split())
    return text[:80] or "New chat"


def _set_session_title_safely(db: SessionDB, session_id: str, title: str) -> None:
    try:
        db.set_session_title(session_id, title)
    except ValueError:
        suffix = session_id[:6]
        trimmed = title[: max(1, 80 - len(suffix) - 4)]
        db.set_session_title(session_id, f"{trimmed} #{suffix}")


def _unique_copy_title(db: SessionDB, title: str | None, session_id: str) -> str:
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


def _duplicate_session(db: SessionDB, session_id: str) -> SessionDetailResponse:
    session = _get_session_or_404(db, session_id)
    new_session_id = uuid4().hex
    model_config = None
    if session.get("model_config"):
        try:
            parsed = json.loads(session["model_config"])
        except (TypeError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, dict):
            model_config = parsed

    db.create_session(
        new_session_id,
        source=session.get("source") or WEB_CHAT_SOURCE,
        model=session.get("model"),
        model_config=model_config,
        system_prompt=session.get("system_prompt"),
    )
    _unique_copy_title(db, session.get("title") or session.get("preview") or "Untitled chat", new_session_id)

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
            reasoning_details=_parse_jsonish(message.get("reasoning_details")),
            codex_reasoning_items=_parse_jsonish(message.get("codex_reasoning_items")),
            codex_message_items=_parse_jsonish(message.get("codex_message_items")),
        )
        if message.get("id") is not None:
            message_id_map[int(message["id"])] = int(new_message_id)

    _copy_session_git_changes(
        db,
        source_session_id=session_id,
        target_session_id=new_session_id,
        message_id_map=message_id_map,
    )
    changes_by_message = _session_git_changes_by_message(db, new_session_id)

    duplicated = _get_session_or_404(db, new_session_id)
    return SessionDetailResponse(
        session=_serialize_session(duplicated),
        messages=_serialize_messages(db.get_messages(new_session_id), changes_by_message=changes_by_message),
    )


def _serialize_session(session: dict[str, Any]) -> WebChatSession:
    created_at = _iso_from_epoch(session.get("started_at"))
    updated_at = _iso_from_epoch(session.get("last_active") or session.get("started_at"))
    return WebChatSession(
        id=session["id"],
        title=session.get("title") or session.get("preview") or "New chat",
        preview=session.get("preview") or "",
        source=session.get("source"),
        model=session.get("model"),
        reasoningEffort=_session_reasoning_effort(session),
        workspace=_session_workspace(session),
        messageCount=session.get("message_count", 0),
        createdAt=created_at,
        updatedAt=updated_at,
    )


def _message_attachments(message: dict[str, Any]) -> list[WebChatAttachment]:
    items = _parse_jsonish(message.get("codex_message_items"))
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
            attachments.append(_attachment_with_runtime_state(WebChatAttachment(**metadata)))
        except Exception:
            continue
    return attachments


def _message_parts(message: dict[str, Any]) -> list[WebChatPart]:
    parts: list[WebChatPart] = []
    attachments = _message_attachments(message)
    if attachments:
        parts.append(WebChatPart(type="media", attachments=attachments))
    if message.get("reasoning") or message.get("reasoning_content"):
        parts.append(WebChatPart(type="reasoning", text=message.get("reasoning") or message.get("reasoning_content")))
    if message.get("content") and message.get("role") != "tool":
        parts.append(WebChatPart(type="text", text=message["content"]))
    if message.get("role") == "tool":
        parts.append(WebChatPart(type="tool", name=message.get("tool_name"), output=_parse_jsonish(message.get("content"))))
    elif message.get("tool_name") or message.get("tool_calls"):
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            for tool_call in tool_calls:
                parts.append(WebChatPart(type="tool", name=_tool_call_name(tool_call) or message.get("tool_name"), input=tool_call))
        else:
            parts.append(WebChatPart(type="tool", name=message.get("tool_name"), input=tool_calls))
    return parts


def _serialize_message(message: dict[str, Any]) -> WebChatMessage:
    return WebChatMessage(
        id=str(message["id"]),
        role=message.get("role"),
        parts=_message_parts(message),
        createdAt=_iso_from_epoch(message.get("timestamp")),
        reasoning=message.get("reasoning") or message.get("reasoning_content"),
        toolName=message.get("tool_name"),
        toolCalls=message.get("tool_calls"),
    )


def _parse_jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    text = value.strip()
    if not text or text[0] not in "[{":
        return value

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _tool_call_name(tool_call: Any) -> str | None:
    if not isinstance(tool_call, dict):
        return None

    function = tool_call.get("function")
    if isinstance(function, dict) and isinstance(function.get("name"), str):
        return function["name"]
    if isinstance(tool_call.get("name"), str):
        return tool_call["name"]
    return None


def _tool_call_id(tool_call: Any) -> str | None:
    if not isinstance(tool_call, dict):
        return None

    value = tool_call.get("id") or tool_call.get("tool_call_id")
    return str(value) if value else None


def _attach_tool_output(messages: list[WebChatMessage], tool_message: dict[str, Any]) -> bool:
    output = _parse_jsonish(tool_message.get("content"))
    tool_call_id = str(tool_message.get("tool_call_id") or "")
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

            if tool_call_id and _tool_call_id(part.input) == tool_call_id:
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


def _serialize_messages(
    messages: list[dict[str, Any]],
    *,
    changes_by_message: dict[str, WebChatWorkspaceChanges] | None = None,
) -> list[WebChatMessage]:
    serialized: list[WebChatMessage] = []
    for message in messages:
        if message.get("role") == "tool" and _attach_tool_output(serialized, message):
            continue
        web_message = _serialize_message(message)
        changes = (changes_by_message or {}).get(str(message.get("id")))
        if changes and changes.files:
            web_message.parts.append(WebChatPart(type="changes", changes=changes.model_dump()))
        serialized.append(web_message)
    return serialized



def _get_session_or_404(db: SessionDB, session_id: str) -> dict[str, Any]:
    session = db._get_session_rich_row(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


def _session_model_config(session: dict[str, Any] | None) -> dict[str, Any]:
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


def _session_workspace(session: dict[str, Any] | None) -> str | None:
    config = _session_model_config(session)
    value = config.get("workspace")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _session_reasoning_effort(session: dict[str, Any] | None) -> str | None:
    config = _session_model_config(session)
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


def _resolve_codex_access_token() -> str | None:
    try:
        from hermes_cli.auth import resolve_codex_runtime_credentials

        creds = resolve_codex_runtime_credentials(refresh_if_expiring=True)
    except Exception:
        return None

    token = creds.get("api_key") if isinstance(creds, dict) else None
    return token.strip() if isinstance(token, str) and token.strip() else None


def _available_model_ids() -> list[str]:
    try:
        from hermes_cli.codex_models import DEFAULT_CODEX_MODELS, get_codex_model_ids

        model_ids = get_codex_model_ids(access_token=_resolve_codex_access_token())
        return [model_id for model_id in model_ids if model_id] or list(DEFAULT_CODEX_MODELS)
    except Exception:
        return [
            "gpt-5.5",
            "gpt-5.4-mini",
            "gpt-5.4",
            "gpt-5.3-codex",
            "gpt-5.2-codex",
            "gpt-5.1-codex-max",
            "gpt-5.1-codex-mini",
        ]


def _model_reasoning_efforts(model_id: str | None) -> list[str]:
    normalized = str(model_id or "").strip().lower()
    if not normalized:
        return ["low", "medium", "high"]
    if normalized in {"gpt-5-pro", "gpt-5.4-pro"}:
        return ["high"]
    if normalized.startswith("gpt-5.4"):
        return ["none", "low", "medium", "high", "xhigh"]
    if normalized == "gpt-5.3-codex":
        return ["low", "medium", "high", "xhigh"]
    if normalized.startswith("gpt-5.1"):
        return ["none", "low", "medium", "high"]
    if normalized.startswith("gpt-5"):
        return ["low", "medium", "high"]
    return ["low", "medium", "high"]


def _default_reasoning_effort(model_id: str | None) -> str | None:
    normalized = str(model_id or "").strip().lower()
    efforts = _model_reasoning_efforts(normalized)
    if normalized in {"gpt-5-pro", "gpt-5.4-pro"}:
        return "high"
    if normalized.startswith("gpt-5.4") or normalized.startswith("gpt-5.1"):
        return "none" if "none" in efforts else "medium"
    if "medium" in efforts:
        return "medium"
    return efforts[0] if efforts else None


def _workspace_root(workspace: str | None = None) -> Path | None:
    candidate = Path(workspace or os.getcwd()).expanduser()
    try:
        root = subprocess.run(
            ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except Exception:
        return None
    return Path(root) if root else None


def _workspace_changes(workspace: str | None = None) -> WebChatWorkspaceChanges:
    root = _workspace_root(workspace)
    if not root:
        return WebChatWorkspaceChanges(files=[], totalFiles=0, totalAdditions=0, totalDeletions=0)

    try:
        numstat_result = subprocess.run(
            ["git", "-C", str(root), "diff", "--numstat", "HEAD", "--"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        status_result = subprocess.run(
            ["git", "-C", str(root), "diff", "--name-status", "HEAD", "--"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return WebChatWorkspaceChanges(files=[], totalFiles=0, totalAdditions=0, totalDeletions=0)

    statuses = _git_name_statuses(status_result.stdout)
    files: list[WebChatFileChange] = []
    seen_paths: set[str] = set()
    for line in numstat_result.stdout.splitlines():
        additions, deletions, path = line.split("\t", 2)
        if additions == "-" or deletions == "-":
            add_count = 0
            delete_count = 0
        else:
            add_count = int(additions)
            delete_count = int(deletions)
        files.append(WebChatFileChange(path=path, status=statuses.get(path, "edited"), additions=add_count, deletions=delete_count))
        seen_paths.add(path)

    for path in _git_untracked_files(root):
        if path in seen_paths:
            continue
        files.append(WebChatFileChange(path=path, status="created", additions=_count_text_lines(root / path), deletions=0))

    return WebChatWorkspaceChanges(
        files=files,
        totalFiles=len(files),
        totalAdditions=sum(file.additions for file in files),
        totalDeletions=sum(file.deletions for file in files),
    )


def _git_name_statuses(output: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    labels = {
        "A": "created",
        "M": "edited",
        "D": "deleted",
        "R": "renamed",
        "C": "copied",
    }
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        code = parts[0][:1]
        path = parts[-1]
        statuses[path] = labels.get(code, "edited")
    return statuses


def _git_untracked_files(root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return []
    return [line for line in result.stdout.splitlines() if line]


def _count_text_lines(path: Path) -> int:
    try:
        data = path.read_bytes()
    except Exception:
        return 0
    if b"\0" in data:
        return 0
    text = data.decode("utf-8", errors="ignore")
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def _model_capabilities() -> list[WebChatModelCapability]:
    capabilities: list[WebChatModelCapability] = []
    for model_id in _available_model_ids():
        capabilities.append(
            WebChatModelCapability(
                id=model_id,
                label=model_id,
                reasoningEfforts=_model_reasoning_efforts(model_id),
                defaultReasoningEffort=_default_reasoning_effort(model_id),
            )
        )
    return capabilities


def _default_model_id() -> str | None:
    model_ids = _available_model_ids()
    return model_ids[0] if model_ids else None


def _resolve_requested_model(model_id: str | None, *, session: dict[str, Any] | None = None) -> str | None:
    requested = str(model_id or "").strip()
    if requested:
        return requested
    session_model = str((session or {}).get("model") or "").strip()
    if session_model:
        return session_model
    return _default_model_id()


def _resolve_requested_reasoning_effort(
    model_id: str | None,
    reasoning_effort: str | None,
    *,
    session: dict[str, Any] | None = None,
) -> str | None:
    supported = _model_reasoning_efforts(model_id)
    requested = str(reasoning_effort or "").strip().lower()
    if requested in supported:
        return requested

    session_reasoning = _session_reasoning_effort(session)
    if session_reasoning in supported:
        return session_reasoning

    default_effort = _default_reasoning_effort(model_id)
    if default_effort in supported:
        return default_effort

    if "medium" in supported:
        return "medium"
    return supported[0] if supported else None


def _list_non_empty_sessions(db: SessionDB, limit: int, offset: int) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    db_offset = 0
    batch_size = MAX_SESSION_LIMIT

    while len(sessions) < offset + limit:
        batch = db.list_sessions_rich(limit=batch_size, offset=db_offset)
        if not batch:
            break
        for session in batch:
            if session.get("message_count", 0) <= 0:
                continue
            sessions.append(_session_with_tip_config(db, session))
        db_offset += len(batch)

    return sessions[offset:offset + limit]


def _session_with_tip_config(db: SessionDB, session: dict[str, Any]) -> dict[str, Any]:
    if not session.get("_lineage_root_id"):
        return session

    tip_session_id = session.get("id")
    if not isinstance(tip_session_id, str) or not tip_session_id:
        return session

    tip_session = db._get_session_rich_row(tip_session_id)
    if not tip_session:
        return session

    return {**session, "model_config": tip_session.get("model_config")}


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(
    limit: int = Query(default=50, ge=1, le=MAX_SESSION_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> SessionListResponse:
    db = _db()
    sessions = _list_non_empty_sessions(db, limit=limit, offset=offset)
    return SessionListResponse(sessions=[_serialize_session(session) for session in sessions])


@router.get("/capabilities", response_model=WebChatCapabilitiesResponse)
def get_capabilities() -> WebChatCapabilitiesResponse:
    return WebChatCapabilitiesResponse(
        provider="codex",
        defaultModel=_default_model_id(),
        models=_model_capabilities(),
    )


@router.get("/profiles", response_model=WebChatProfilesResponse)
def get_profiles() -> WebChatProfilesResponse:
    return _list_web_chat_profiles()


@router.post("/profiles/active", response_model=SwitchProfileResponse)
def switch_profile(payload: SwitchProfileRequest) -> SwitchProfileResponse:
    return _switch_web_chat_profile(payload)


@router.get("/workspaces", response_model=WebChatWorkspacesResponse)
def get_workspaces() -> WebChatWorkspacesResponse:
    return _list_web_chat_workspaces()


@router.get("/workspace-directories", response_model=DirectorySuggestionsResponse)
def get_workspace_directories(prefix: str = Query(min_length=1, max_length=4096)) -> DirectorySuggestionsResponse:
    return DirectorySuggestionsResponse(suggestions=_directory_suggestions(prefix))


@router.post("/workspaces", status_code=status.HTTP_201_CREATED, response_model=WebChatWorkspaceResponse)
def create_workspace(payload: SaveWorkspaceRequest) -> WebChatWorkspaceResponse:
    return WebChatWorkspaceResponse(workspace=_create_managed_workspace(payload))


@router.patch("/workspaces/{workspace_id}", response_model=WebChatWorkspaceResponse)
def update_workspace(workspace_id: str, payload: SaveWorkspaceRequest) -> WebChatWorkspaceResponse:
    return WebChatWorkspaceResponse(workspace=_update_managed_workspace(workspace_id, payload))


@router.delete("/workspaces/{workspace_id}", response_model=DeleteSessionResponse)
def delete_workspace(workspace_id: str) -> DeleteSessionResponse:
    _delete_managed_workspace(workspace_id)
    return DeleteSessionResponse(ok=True)


@router.post("/attachments", status_code=status.HTTP_201_CREATED, response_model=UploadAttachmentsResponse)
async def upload_attachments(
    files: list[UploadFile] = File(...),
    workspace: str | None = Form(default=None),
) -> UploadAttachmentsResponse:
    if len(files) > MAX_ATTACHMENTS_PER_REQUEST:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Too many attachments")
    return UploadAttachmentsResponse(attachments=[await _store_upload(file, workspace) for file in files])


@router.get("/attachments/{attachment_id}", response_model=WebChatAttachment)
def get_attachment(attachment_id: str, workspace: str | None = None) -> WebChatAttachment:
    return _load_attachment(attachment_id, workspace)


@router.get("/attachments/{attachment_id}/content")
def get_attachment_content(attachment_id: str, workspace: str | None = None) -> FileResponse:
    attachment = _load_attachment(attachment_id, workspace)
    path = Path(attachment.path)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment file not found")
    return FileResponse(path, media_type=attachment.mediaType, filename=attachment.name, content_disposition_type="inline")


@router.get("/workspace-changes", response_model=WebChatWorkspaceChanges, response_model_exclude_none=True)
def get_workspace_changes(workspace: str | None = None) -> WebChatWorkspaceChanges:
    validated = _validate_workspace(workspace)
    return _workspace_changes(str(validated) if validated else None)



@router.post("/sessions", status_code=status.HTTP_201_CREATED, response_model=SessionDetailResponse)
def create_session(payload: CreateSessionRequest) -> SessionDetailResponse:
    db = _db()
    session_id = uuid4().hex
    title = _title_from_message(payload.message)

    db.create_session(session_id, source=WEB_CHAT_SOURCE)
    db.set_session_title(session_id, title)
    db.append_message(session_id, "user", payload.message)

    session = _get_session_or_404(db, session_id)
    messages = db.get_messages(session_id)
    return SessionDetailResponse(
        session=_serialize_session(session),
        messages=_serialize_messages(messages),
    )


@router.patch("/sessions/{session_id}", response_model=SessionDetailResponse)
def rename_session(session_id: str, payload: RenameSessionRequest) -> SessionDetailResponse:
    db = _db()
    _get_session_or_404(db, session_id)
    try:
        db.set_session_title(session_id, payload.title)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session = _get_session_or_404(db, session_id)
    return SessionDetailResponse(
        session=_serialize_session(session),
        messages=_serialize_messages(db.get_messages(session_id)),
    )


@router.patch("/sessions/{session_id}/messages/{message_id}", response_model=SessionDetailResponse)
def edit_message(session_id: str, message_id: str, payload: EditMessageRequest) -> SessionDetailResponse:
    db = _db()
    _get_session_or_404(db, session_id)
    _edit_user_message(db, session_id, message_id, payload.content)
    session = _get_session_or_404(db, session_id)
    return SessionDetailResponse(
        session=_serialize_session(session),
        messages=_serialize_messages(db.get_messages(session_id)),
    )


@router.delete("/sessions/{session_id}", response_model=DeleteSessionResponse)
def delete_session(session_id: str) -> DeleteSessionResponse:
    db = _db()
    if not db.delete_session(session_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    _delete_session_git_changes(db, session_id)
    return DeleteSessionResponse(ok=True)


@router.post("/sessions/{session_id}/duplicate", status_code=status.HTTP_201_CREATED, response_model=SessionDetailResponse)
def duplicate_session(session_id: str) -> SessionDetailResponse:
    return _duplicate_session(_db(), session_id)


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: str, includeWorkspaceChanges: bool = Query(default=False)) -> SessionDetailResponse:
    db = _db()
    session = _get_session_or_404(db, session_id)
    messages = db.get_messages(session_id)
    changes_by_message = _session_git_changes_by_message(db, session_id) if includeWorkspaceChanges else None
    return SessionDetailResponse(
        session=_serialize_session(session),
        messages=_serialize_messages(messages, changes_by_message=changes_by_message),
    )


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED, response_model=StartRunResponse)
def start_run(payload: StartRunRequest) -> StartRunResponse:
    return run_manager.start(payload)


@router.get("/runs/{run_id}/events")
def run_events(run_id: str) -> StreamingResponse:
    return StreamingResponse(run_manager.events(run_id), media_type="text/event-stream")


@router.post("/runs/{run_id}/stop", response_model=StopRunResponse)
def stop_run(run_id: str) -> StopRunResponse:
    return run_manager.stop(run_id)
