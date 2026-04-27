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
    baseline_change_fingerprint: str | None = None
    stop_requested: threading.Event = field(default_factory=threading.Event)
    interrupt_agent: Callable[[str | None], None] | None = None
    steer_agent: Callable[[str], None] | None = None
    request_prompt: Callable[[WebChatPrompt, float], str | None] | None = field(default=None, repr=False)


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

        user_message_id = None
        if not request.editedMessageId:
            message_items = []
            if request.clientMessageId:
                message_items.append({"type": "web_chat_client_message", "clientMessageId": request.clientMessageId})
            message_items.extend(
                {"type": "web_chat_attachment", "attachment": attachment.model_dump()}
                for attachment in attachments
            )
            user_message_id = db.append_message(
                session_id,
                "user",
                request.input,
                codex_message_items=message_items or None,
            )

        baseline_git_status = self._services.git_status_porcelain(workspace_path) if workspace_path else None
        baseline_change_fingerprint = self._services.workspace_change_fingerprint(workspace_path) if workspace_path else None

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
            baseline_change_fingerprint=baseline_change_fingerprint,
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
        message_id = self._services.db().append_message(
            active.context.session_id,
            "system",
            None,
            codex_message_items=[{"type": "web_chat_steer", "text": request.text}],
        )
        self._emit(active, {"type": "run.steered", "messageId": str(message_id), "text": request.text})
        return SteerRunResponse(
            runId=run_id,
            sessionId=active.context.session_id,
            accepted=True,
            messageId=str(message_id),
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
        items = message.get("codex_message_items")
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except json.JSONDecodeError:
                return None
        if not isinstance(items, list):
            return None

        for item in items:
            if not isinstance(item, dict) or item.get("type") != "web_chat_client_message":
                continue
            value = item.get("clientMessageId")
            if isinstance(value, str) and value:
                return value
        return None

    def _emit(self, active: ActiveRun, event: dict[str, Any]) -> None:
        with active.event_condition:
            event_id = active.next_event_id
            active.next_event_id += 1
            active.events.append({"id": event_id, "runId": active.context.run_id, "sessionId": active.context.session_id, **event})
            active.event_condition.notify_all()

    def _finish(self, active: ActiveRun, status: str) -> None:
        active.status = status
        active.terminal = True
        with active.event_condition:
            active.event_condition.notify_all()

    def _iso_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

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

    def _prompt_items(self, active: ActiveRun) -> list[dict[str, Any]] | None:
        prompts = list(active.prompts.values())
        if not prompts:
            return None
        return [{"type": "web_chat_prompt", "prompt": prompt.model_dump()} for prompt in prompts]

    def _run(self, active: ActiveRun) -> None:
        self._emit(active, {"type": "run.started"})
        assistant_message_id: int | None = None
        try:
            active.context.request_prompt = lambda prompt, timeout_seconds=600: self._request_prompt(active, prompt, timeout_seconds)
            final_text = self._executor(active.context, lambda event: self._emit(active, event))
            if active.context.stop_requested.is_set():
                interrupted_text = "Chat interrupted."
                assistant_message_id = self._services.db().append_message(
                    active.context.session_id,
                    "assistant",
                    interrupted_text,
                    codex_message_items=self._prompt_items(active),
                )
                changes = self._services.persist_run_workspace_changes(active.context, assistant_message_id)
                self._emit(
                    active,
                    {
                        "type": "message.completed",
                        "content": interrupted_text,
                        "changes": changes.model_dump() if changes else None,
                    },
                )
                self._emit(active, {"type": "run.stopped"})
                self._finish(active, "stopped")
                return
            if final_text:
                assistant_message_id = self._services.db().append_message(
                    active.context.session_id,
                    "assistant",
                    final_text,
                    codex_message_items=self._prompt_items(active),
                )
                changes = self._services.persist_run_workspace_changes(active.context, assistant_message_id)
                self._emit(
                    active,
                    {
                        "type": "message.completed",
                        "content": final_text,
                        "changes": changes.model_dump() if changes else None,
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
