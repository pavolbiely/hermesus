"""Native web chat API for the Hermes dashboard.

This module exposes JSON/SSE endpoints for a first-class web chat UI. It keeps
``SessionDB`` as the source of truth and intentionally does not use the legacy
xterm/PTY dashboard chat transport.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from hermes_state import SessionDB

router = APIRouter(prefix="/api/web-chat", tags=["web-chat"])

WEB_CHAT_SOURCE = "web-chat"
MAX_SESSION_LIMIT = 100
RunExecutor = Callable[["RunContext", Callable[[dict[str, Any]], None]], str]


class WebChatPart(BaseModel):
    type: Literal["text", "reasoning", "tool", "media", "approval"]
    text: str | None = None
    name: str | None = None
    status: str | None = None
    input: Any | None = None
    output: Any | None = None
    url: str | None = None
    mediaType: str | None = None
    approvalId: str | None = None


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


class SessionListResponse(BaseModel):
    sessions: list[WebChatSession]


class SessionDetailResponse(BaseModel):
    session: WebChatSession
    messages: list[WebChatMessage]


class CreateSessionRequest(BaseModel):
    message: str = Field(min_length=1, max_length=65536)


class StartRunRequest(BaseModel):
    sessionId: str | None = None
    input: str = Field(min_length=1, max_length=65536)
    workspace: str | None = None
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
    model: str | None = None
    reasoning_effort: str | None = None
    provider: str | None = None
    enabled_toolsets: list[str] | None = None
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

        if request.sessionId:
            db.update_session_model_settings(
                session_id,
                model=effective_model,
                model_config_updates={"reasoningEffort": effective_reasoning_effort},
            )
        else:
            db.create_session(
                session_id,
                source=WEB_CHAT_SOURCE,
                model=effective_model,
                model_config={"reasoningEffort": effective_reasoning_effort} if effective_reasoning_effort else None,
            )
            _set_session_title_safely(db, session_id, _title_from_message(request.input))

        db.append_message(session_id, "user", request.input)

        run_id = uuid4().hex
        context = RunContext(
            run_id=run_id,
            session_id=session_id,
            input=request.input,
            workspace=request.workspace,
            model=effective_model,
            reasoning_effort=effective_reasoning_effort,
            provider=request.provider,
            enabled_toolsets=request.enabledToolsets,
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
        try:
            final_text = self._executor(active.context, lambda event: self._emit(active, event))
            if active.context.stop_requested.is_set():
                self._emit(active, {"type": "run.stopped"})
                return
            if final_text:
                _db().append_message(active.context.session_id, "assistant", final_text)
                self._emit(active, {"type": "message.completed", "content": final_text})
            self._emit(active, {"type": "run.completed"})
        except Exception as exc:
            self._emit(active, {"type": "run.failed", "error": str(exc)})
        finally:
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
    )

    result = agent.run_conversation(
        context.input,
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
        messageCount=session.get("message_count", 0),
        createdAt=created_at,
        updatedAt=updated_at,
    )


def _message_parts(message: dict[str, Any]) -> list[WebChatPart]:
    parts: list[WebChatPart] = []
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


def _serialize_messages(messages: list[dict[str, Any]]) -> list[WebChatMessage]:
    serialized: list[WebChatMessage] = []
    for message in messages:
        if message.get("role") == "tool" and _attach_tool_output(serialized, message):
            continue
        serialized.append(_serialize_message(message))
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
        sessions.extend(session for session in batch if session.get("message_count", 0) > 0)
        db_offset += len(batch)

    return sessions[offset:offset + limit]


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


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: str) -> SessionDetailResponse:
    db = _db()
    session = _get_session_or_404(db, session_id)
    messages = db.get_messages(session_id)
    return SessionDetailResponse(
        session=_serialize_session(session),
        messages=_serialize_messages(messages),
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
