"""Run lifecycle management for the native web chat API."""

from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

from fastapi import HTTPException, status

from .models import StartRunRequest, StartRunResponse, StopRunResponse

RunExecutor = Callable[["RunContext", Callable[[dict[str, Any]], None]], str]


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
    interrupt_agent: Callable[[str | None], None] | None = None


@dataclass
class ActiveRun:
    context: RunContext
    events: "queue.Queue[dict[str, Any] | None]" = field(default_factory=queue.Queue)
    thread: threading.Thread | None = None
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class RunManagerServices:
    source: str
    db: Callable[[], Any]
    resolve_requested_model: Callable[..., str]
    resolve_requested_reasoning_effort: Callable[..., str | None]
    validate_workspace: Callable[[str | None], Any]
    session_workspace: Callable[[Any], str | None]
    validate_profile: Callable[[str | None], str | None]
    resolve_attachments: Callable[[list[str] | None, str | None], list[Any]]
    validate_edited_message_continuation: Callable[[Any, str, str], None]
    input_with_attachment_context: Callable[[str, list[Any]], str]
    set_session_title_safely: Callable[[Any, str, str], None]
    title_from_message: Callable[[str], str]
    git_status_porcelain: Callable[[str | None], str]
    persist_run_workspace_changes: Callable[[RunContext, int | None], None]
    agent_executor: RunExecutor


class RunManager:
    def __init__(self, services: RunManagerServices, executor: RunExecutor | None = None):
        self._runs: dict[str, ActiveRun] = {}
        self._lock = threading.Lock()
        self._services = services
        self._executor = executor or services.agent_executor

    def start(self, request: StartRunRequest) -> StartRunResponse:
        db = self._services.db()
        session_id = request.sessionId or uuid4().hex
        session = None
        if request.sessionId:
            session = db.get_session(request.sessionId)
            if not session:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
            db.reopen_session(request.sessionId)
        else:
            session = None

        effective_model = self._services.resolve_requested_model(request.model, session=session)
        effective_reasoning_effort = self._services.resolve_requested_reasoning_effort(
            effective_model,
            request.reasoningEffort,
            session=session,
        )
        provided_fields = getattr(request, "model_fields_set", None)
        if provided_fields is None:
            provided_fields = getattr(request, "__fields_set__", set())
        workspace_provided = "workspace" in provided_fields
        workspace = self._services.validate_workspace(request.workspace) if workspace_provided else self._services.validate_workspace(self._services.session_workspace(session))
        workspace_path = str(workspace) if workspace else None
        profile = self._services.validate_profile(request.profile)
        attachments = self._services.resolve_attachments(request.attachments, workspace_path)
        if request.editedMessageId:
            if not request.sessionId:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Edited message requires an existing chat.")
            self._services.validate_edited_message_continuation(db, session_id, request.editedMessageId)
        if attachments and not workspace_path:
            attachment_workspaces = {attachment.workspace for attachment in attachments if attachment.workspace}
            if len(attachment_workspaces) == 1:
                workspace = self._services.validate_workspace(next(iter(attachment_workspaces)))
                workspace_path = str(workspace) if workspace else None
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select a workspace before sending attachments.")
        effective_input = self._services.input_with_attachment_context(request.input, attachments)

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
                source=self._services.source,
                model=effective_model,
                model_config=model_config_updates,
            )
            self._services.set_session_title_safely(db, session_id, self._services.title_from_message(request.input))

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

        baseline_git_status = self._services.git_status_porcelain(workspace_path) if workspace_path else None

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
        if active.context.interrupt_agent:
            active.context.interrupt_agent("Chat interrupted by user")
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
                interrupted_text = "Chat interrupted."
                assistant_message_id = self._services.db().append_message(active.context.session_id, "assistant", interrupted_text)
                self._services.persist_run_workspace_changes(active.context, assistant_message_id)
                self._emit(active, {"type": "message.completed", "content": interrupted_text})
                self._emit(active, {"type": "run.stopped"})
                return
            if final_text:
                assistant_message_id = self._services.db().append_message(active.context.session_id, "assistant", final_text)
                self._services.persist_run_workspace_changes(active.context, assistant_message_id)
                self._emit(active, {"type": "message.completed", "content": final_text})
            self._emit(active, {"type": "run.completed"})
        except Exception as exc:
            self._emit(active, {"type": "run.failed", "error": str(exc)})
        finally:
            if assistant_message_id is None:
                self._services.persist_run_workspace_changes(active.context, None)
            active.events.put(None)
