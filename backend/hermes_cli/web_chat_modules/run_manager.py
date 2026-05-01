"""Run lifecycle management for the native web chat API."""

from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

from fastapi import HTTPException, status

from .models import (
    ActiveRunSummary,
    RespondRunPromptRequest,
    RespondRunPromptResponse,
    StartRunRequest,
    StartRunResponse,
    SteerRunRequest,
    SteerRunResponse,
    StopRunResponse,
    WebChatPrompt,
    WebChatWorkspaceChanges,
)
from .run_events import MESSAGE_ITEMS_FIELD, client_message_id_from_message, system_event_part, task_plan_from_event
from .sessions import session_provider

RunExecutor = Callable[["RunContext", Callable[[dict[str, Any]], None]], str]


@dataclass
class RunContext:
    run_id: str
    session_id: str
    input: str
    workspace: str | None = None
    source_workspace: str | None = None
    source_git_root: str | None = None
    isolated_workspace: str | None = None
    profile: str | None = None
    attachments: list[str] | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    provider: str | None = None
    enabled_toolsets: list[str] | None = None
    baseline_git_status: str | None = None
    baseline_change_fingerprint: str | None = None
    baseline_workspace_snapshot: dict[str, dict[str, Any]] | None = None
    stop_requested: threading.Event = field(default_factory=threading.Event)
    interrupt_agent: Callable[[str | None], None] | None = None
    steer_agent: Callable[[str], None] | None = None
    request_prompt: Callable[[WebChatPrompt, float], str | None] | None = field(default=None, repr=False)
    usage_metrics: dict[str, Any] | None = None


@dataclass
class ActiveRun:
    context: RunContext
    client_message_id: str | None = None
    user_message_id: str | None = None
    prompts: dict[str, WebChatPrompt] = field(default_factory=dict)
    prompt_responses: dict[str, "queue.Queue[str | None]"] = field(default_factory=dict)
    thread: threading.Thread | None = None
    created_at: float = field(default_factory=time.time)
    events: list[dict[str, Any]] = field(default_factory=list)
    event_condition: threading.Condition = field(default_factory=lambda: threading.Condition(threading.Lock()))
    status: str = "running"
    terminal: bool = False
    next_event_id: int = 1
    tool_duration_ms: int = 0
    prompt_wait_duration_ms: int = 0
    tool_started_at: dict[str, list[float]] = field(default_factory=dict)
    latest_task_plan: dict[str, Any] | None = None


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
    workspace_change_fingerprint: Callable[[str | None], str | None]
    workspace_file_snapshot: Callable[[str | None], dict[str, dict[str, Any]] | None]
    ensure_session_worktree: Callable[[Any, str, str | None, str | None], Any | None]
    persist_run_workspace_changes: Callable[[RunContext, int | None], WebChatWorkspaceChanges | None]
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

        if request.clientMessageId and not request.editedMessageId:
            existing_message = self._user_message_for_client_message_id(db, session_id, request.clientMessageId)
            existing_run = self._run_for_client_message_id(session_id, request.clientMessageId)
            if existing_message and existing_run:
                return StartRunResponse(
                    sessionId=session_id,
                    runId=existing_run.context.run_id,
                    userMessageId=str(existing_message["id"]),
                )
            if existing_message:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Message was already submitted. Refresh the chat before retrying.",
                )

        effective_provider = request.provider or session_provider(session)
        model_config_updates = {"reasoningEffort": effective_reasoning_effort}
        if effective_provider:
            model_config_updates["provider"] = effective_provider
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

        execution_workspace_path = workspace_path

        user_message_id = None
        if not request.editedMessageId:
            message_items = []
            if request.clientMessageId:
                message_items.append({"type": "web_chat_client_message", "clientMessageId": request.clientMessageId})
            message_items.extend(
                {"type": "web_chat_attachment", "attachment": attachment.model_dump()}
                for attachment in attachments
            )
            user_message_id = self._append_message(
                db,
                session_id,
                "user",
                request.input,
                message_items=message_items or None,
            )

        baseline_git_status = self._services.git_status_porcelain(execution_workspace_path) if execution_workspace_path else None
        baseline_change_fingerprint = self._services.workspace_change_fingerprint(execution_workspace_path) if execution_workspace_path else None
        baseline_workspace_snapshot = self._services.workspace_file_snapshot(execution_workspace_path) if execution_workspace_path else None

        run_id = uuid4().hex
        context = RunContext(
            run_id=run_id,
            session_id=session_id,
            input=effective_input,
            workspace=execution_workspace_path,
            source_workspace=workspace_path,
            source_git_root=None,
            isolated_workspace=None,
            profile=profile,
            attachments=[attachment.id for attachment in attachments] or None,
            model=effective_model,
            reasoning_effort=effective_reasoning_effort,
            provider=effective_provider,
            enabled_toolsets=request.enabledToolsets,
            baseline_git_status=baseline_git_status,
            baseline_change_fingerprint=baseline_change_fingerprint,
            baseline_workspace_snapshot=baseline_workspace_snapshot,
        )
        active = ActiveRun(
            context=context,
            client_message_id=request.clientMessageId if not request.editedMessageId else None,
            user_message_id=str(user_message_id) if user_message_id else None,
        )
        active.thread = threading.Thread(target=self._run, args=(active,), daemon=True)
        with self._lock:
            self._runs[run_id] = active
        active.thread.start()
        return StartRunResponse(sessionId=session_id, runId=run_id, userMessageId=str(user_message_id) if user_message_id else None)

    def events(self, run_id: str, after: int | None = None):
        active = self._get(run_id)
        cursor = max((after or 0) + 1, 1)

        def event_stream():
            nonlocal cursor
            while True:
                with active.event_condition:
                    while active.next_event_id <= cursor and not active.terminal:
                        active.event_condition.wait(timeout=15)
                        if active.next_event_id <= cursor and not active.terminal:
                            yield ": keepalive\n\n"
                    events = [event for event in active.events if event["id"] >= cursor]
                    terminal = active.terminal

                for event in events:
                    cursor = int(event["id"]) + 1
                    yield f"id: {event['id']}\n"
                    yield f"event: {event['type']}\n"
                    yield f"data: {json.dumps(event, separators=(',', ':'))}\n\n"

                if terminal and cursor >= active.next_event_id:
                    break

        return event_stream()

    def stop(self, run_id: str) -> StopRunResponse:
        active = self._get(run_id)
        active.context.stop_requested.set()
        active.status = "stopping"
        self._cancel_pending_prompts(active)
        if active.context.interrupt_agent:
            active.context.interrupt_agent("Chat interrupted by user")
        self._emit(active, {"type": "run.stopping"})
        return StopRunResponse(runId=run_id, stopped=True)

    def steer(self, run_id: str, request: SteerRunRequest) -> SteerRunResponse:
        active = self._get(run_id)
        if active.terminal or not active.thread or not active.thread.is_alive():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Run is no longer active")

        steer_agent = active.context.steer_agent
        if not steer_agent:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Run does not support live steering")

        steer_agent(request.text)
        emitted_event = self._emit(active, {"type": "run.steered", "text": request.text})
        message_id = emitted_event.get("messageId")
        return SteerRunResponse(
            runId=run_id,
            sessionId=active.context.session_id,
            accepted=True,
            messageId=str(message_id) if message_id else None,
        )

    def respond_prompt(self, run_id: str, prompt_id: str, request: RespondRunPromptRequest) -> RespondRunPromptResponse:
        active = self._get(run_id)
        with self._lock:
            prompt = active.prompts.get(prompt_id)
            response_queue = active.prompt_responses.get(prompt_id)
            if not prompt:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")
            if prompt.status != "pending":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Prompt is no longer pending")
            if (request.choice is None) == (request.text is None):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Prompt response requires exactly one of choice or text")
            if request.choice:
                allowed_choices = {choice.id for choice in prompt.choices}
                if request.choice not in allowed_choices:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid prompt choice")
            if request.text and not prompt.freeText:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Prompt does not accept free-text responses")

            prompt.status = "answered"
            prompt.selectedChoice = request.choice
            prompt.responseText = request.text
            prompt.answeredAt = self._iso_now()

        if response_queue:
            response_queue.put(request.choice or request.text)
        self._emit(active, {"type": "prompt.answered", "prompt": prompt.model_dump()})
        return RespondRunPromptResponse(prompt=prompt)

    def has_running_runs(self) -> bool:
        with self._lock:
            return any(active.thread and active.thread.is_alive() for active in self._runs.values())

    def active_run_for_session(self, session_id: str) -> ActiveRunSummary | None:
        with self._lock:
            runs = [active for active in self._runs.values() if active.context.session_id == session_id and not active.terminal]
            if not runs:
                return None
            active = max(runs, key=lambda run: run.created_at)
            prompts = list(active.prompts.values())
            return ActiveRunSummary(
                runId=active.context.run_id,
                sessionId=active.context.session_id,
                status=active.status,  # type: ignore[arg-type]
                prompts=prompts,
            )

    def _get(self, run_id: str) -> ActiveRun:
        with self._lock:
            active = self._runs.get(run_id)
        if not active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
        return active

    def _run_for_client_message_id(self, session_id: str, client_message_id: str) -> ActiveRun | None:
        with self._lock:
            candidates = [
                active for active in self._runs.values()
                if active.context.session_id == session_id and active.client_message_id == client_message_id
            ]
        if not candidates:
            return None
        return max(candidates, key=lambda run: run.created_at)

    def _user_message_for_client_message_id(self, db: Any, session_id: str, client_message_id: str) -> dict[str, Any] | None:
        for message in db.get_messages(session_id):
            if message.get("role") != "user":
                continue
            if self._message_client_message_id(message) == client_message_id:
                return message
        return None

    def _message_client_message_id(self, message: dict[str, Any]) -> str | None:
        return client_message_id_from_message(message)

    def _emit(self, active: ActiveRun, event: dict[str, Any]) -> dict[str, Any]:
        self._track_event_duration(active, event)
        self._track_task_plan(active, event)
        system_message_id = self._persist_system_event(active, event)
        if system_message_id is not None and not event.get("messageId"):
            event = {**event, "messageId": str(system_message_id)}
        emitted_event = {"runId": active.context.run_id, "sessionId": active.context.session_id, **event}
        with active.event_condition:
            event_id = active.next_event_id
            active.next_event_id += 1
            emitted_event = {"id": event_id, **emitted_event}
            active.events.append(emitted_event)
            active.event_condition.notify_all()
        return emitted_event

    def _track_task_plan(self, active: ActiveRun, event: dict[str, Any]) -> None:
        task_plan = task_plan_from_event(event)
        if task_plan is not None:
            active.latest_task_plan = task_plan

    def _persist_system_event(self, active: ActiveRun, event: dict[str, Any]) -> Any | None:
        system_event = self._system_event_part(active, event)
        if not system_event:
            return None
        return self._append_message(
            self._services.db(),
            active.context.session_id,
            "system",
            None,
            message_items=[{"type": "web_chat_event", "event": system_event}],
        )

    def _system_event_part(self, active: ActiveRun, event: dict[str, Any]) -> dict[str, Any] | None:
        return system_event_part(event, self._iso_now())

    def _track_event_duration(self, active: ActiveRun, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type not in {"tool.started", "tool.completed"}:
            return

        key = str(event.get("name") or "tool")
        now = time.time()
        if event_type == "tool.started":
            active.tool_started_at.setdefault(key, []).append(now)
            return

        starts = active.tool_started_at.get(key)
        if starts:
            active.tool_duration_ms += max(0, round((now - starts.pop()) * 1000))

    def _finish(self, active: ActiveRun, status: str) -> None:
        active.status = status
        active.terminal = True
        with active.event_condition:
            active.event_condition.notify_all()

    def _iso_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _append_message(
        self,
        db: Any,
        session_id: str,
        role: str,
        content: str | None,
        *,
        message_items: list[dict[str, Any]] | None = None,
    ) -> Any:
        """Append a web-chat message using the Hermes storage field.

        SessionDB still names this generic metadata column `codex_message_items`
        for compatibility with existing Hermes history. Keep that storage detail
        behind a provider-neutral web-chat API in this module.
        """
        return db.append_message(
            session_id,
            role,
            content,
            codex_message_items=message_items,
        )

    def _request_prompt(self, active: ActiveRun, prompt: WebChatPrompt, timeout_seconds: float = 600) -> str | None:
        prompt.runId = active.context.run_id
        prompt.sessionId = active.context.session_id
        prompt.createdAt = prompt.createdAt or self._iso_now()
        prompt.expiresAt = prompt.expiresAt or (datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)).isoformat()
        prompt.status = "pending"
        response_queue: "queue.Queue[str | None]" = queue.Queue(maxsize=1)
        with self._lock:
            active.prompts[prompt.id] = prompt
            active.prompt_responses[prompt.id] = response_queue
        self._emit(active, {"type": "prompt.requested", "prompt": prompt.model_dump()})

        wait_started_at = time.time()
        try:
            answer = response_queue.get(timeout=timeout_seconds)
        except queue.Empty:
            with self._lock:
                if prompt.status == "pending":
                    prompt.status = "expired"
                    prompt.answeredAt = self._iso_now()
                    self._emit(active, {"type": "prompt.expired", "prompt": prompt.model_dump()})
            return None
        finally:
            active.prompt_wait_duration_ms += max(0, round((time.time() - wait_started_at) * 1000))
            with self._lock:
                active.prompt_responses.pop(prompt.id, None)

        return answer

    def _cancel_pending_prompts(self, active: ActiveRun) -> None:
        with self._lock:
            pending = [prompt for prompt in active.prompts.values() if prompt.status == "pending"]
            queues = [active.prompt_responses.get(prompt.id) for prompt in pending]
            for prompt in pending:
                prompt.status = "cancelled"
                prompt.answeredAt = self._iso_now()

        for prompt, response_queue in zip(pending, queues):
            if response_queue:
                response_queue.put(None)
            self._emit(active, {"type": "prompt.cancelled", "prompt": prompt.model_dump()})

    def _message_metrics(self, active: ActiveRun, *, generation_duration_ms: int | None = None) -> dict[str, Any]:
        metrics = dict(active.context.usage_metrics or {})
        if generation_duration_ms is not None:
            metrics["generationDurationMs"] = generation_duration_ms
            metrics["toolDurationMs"] = active.tool_duration_ms
            metrics["promptWaitDurationMs"] = active.prompt_wait_duration_ms
            metrics["modelDurationMs"] = max(
                0,
                generation_duration_ms - active.tool_duration_ms - active.prompt_wait_duration_ms,
            )
        return metrics

    def _message_items(self, active: ActiveRun, metrics: dict[str, Any]) -> list[dict[str, Any]] | None:
        items: list[dict[str, Any]] = []
        prompts = list(active.prompts.values())
        items.extend({"type": "web_chat_prompt", "prompt": prompt.model_dump()} for prompt in prompts)
        if active.latest_task_plan:
            items.append({"type": "web_chat_task_plan", "taskPlan": active.latest_task_plan})
        if metrics:
            items.append({"type": "web_chat_metrics", "metrics": metrics})

        return items or None

    def _run(self, active: ActiveRun) -> None:
        self._emit(active, {"type": "run.started"})
        assistant_message_id: int | None = None
        try:
            active.context.request_prompt = lambda prompt, timeout_seconds=600: self._request_prompt(active, prompt, timeout_seconds)
            final_text = self._executor(active.context, lambda event: self._emit(active, event))
            if active.context.stop_requested.is_set():
                self._emit(active, {"type": "run.stopped"})
                self._finish(active, "stopped")
                return

            generation_duration_ms = max(0, round((time.time() - active.created_at) * 1000))
            metrics = self._message_metrics(active, generation_duration_ms=generation_duration_ms)
            if final_text:
                assistant_message_id = self._append_message(
                    self._services.db(),
                    active.context.session_id,
                    "assistant",
                    final_text,
                    message_items=self._message_items(active, metrics),
                )
                changes = self._services.persist_run_workspace_changes(active.context, assistant_message_id)
                self._emit(
                    active,
                    {
                        "type": "message.completed",
                        "content": final_text,
                        "changes": changes.model_dump() if changes else None,
                        "metrics": metrics,
                    },
                )
            self._emit(active, {"type": "run.completed"})
            self._finish(active, "completed")
        except Exception as exc:
            self._emit(active, {"type": "run.failed", "error": str(exc)})
            self._finish(active, "failed")
        finally:
            self._cancel_pending_prompts(active)
            if assistant_message_id is None:
                self._services.persist_run_workspace_changes(active.context, None)
            active.context.interrupt_agent = None
            active.context.steer_agent = None
            self._finish(active, active.status)
