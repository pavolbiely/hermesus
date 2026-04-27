"""Hermes Agent execution helpers for the native web chat API."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from threading import Lock
from typing import Any, Callable
from uuid import uuid4

from .models import WebChatPrompt, WebChatPromptChoice
from .run_manager import RunContext

WEB_CHAT_SOURCE = "web-chat"

_APPROVAL_BRIDGE_LOCK = Lock()
_APPROVAL_BRIDGE_CALLBACKS: list[Callable[..., str]] = []
_APPROVAL_BRIDGE_ORIGINAL_GETTER: Callable[[], Any] | None = None


def _set_web_approval_env(session_id: str) -> Callable[[], None]:
    """Force runtime approval checks into interactive gateway mode for this run.

    The runtime guard decides whether to ask for approval from process env flags,
    not from the callback alone. Without these flags, the web backend is treated
    as non-interactive and dangerous commands can bypass prompt creation.
    """
    updates = {
        "HERMES_EXEC_ASK": "1",
        "HERMES_GATEWAY_SESSION": "1",
        "HERMES_SESSION_KEY": session_id,
    }
    previous = {key: os.environ.get(key) for key in updates}
    os.environ.update(updates)

    def restore() -> None:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    return restore


def _install_terminal_approval_bridge(callback: Callable[..., str]) -> Callable[[], None]:
    """Expose web-chat approval callback to terminal-tool worker threads.

    Hermes' terminal approval callback is thread-local. Web-chat runs can invoke
    terminal tools from helper threads, where that thread-local callback is not
    visible, which falls back to CLI stdin prompts. Keep the thread-local path,
    but add a process-local fallback while this web-chat run is active.
    """
    try:
        import tools.terminal_tool as terminal_tool
    except Exception:
        return lambda: None

    with _APPROVAL_BRIDGE_LOCK:
        global _APPROVAL_BRIDGE_ORIGINAL_GETTER
        if _APPROVAL_BRIDGE_ORIGINAL_GETTER is None:
            _APPROVAL_BRIDGE_ORIGINAL_GETTER = terminal_tool._get_approval_callback

            def bridged_get_approval_callback():
                local_callback = _APPROVAL_BRIDGE_ORIGINAL_GETTER()
                if local_callback is not None:
                    return local_callback
                with _APPROVAL_BRIDGE_LOCK:
                    return _APPROVAL_BRIDGE_CALLBACKS[-1] if _APPROVAL_BRIDGE_CALLBACKS else None

            terminal_tool._get_approval_callback = bridged_get_approval_callback
        _APPROVAL_BRIDGE_CALLBACKS.append(callback)

    def uninstall() -> None:
        with _APPROVAL_BRIDGE_LOCK:
            if callback in _APPROVAL_BRIDGE_CALLBACKS:
                _APPROVAL_BRIDGE_CALLBACKS.remove(callback)

    return uninstall


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _choice_id(index: int) -> str:
    return f"choice_{index}"


def agent_executor(
    context: RunContext,
    emit: Callable[[dict[str, Any]], None],
    *,
    conversation_history: Callable[[str], list[dict[str, str]]],
) -> str:
    """Run a Hermes Agent turn and stream text/tool deltas to the web UI."""
    from hermes_constants import parse_reasoning_effort
    from hermes_cli.config import load_config
    from hermes_cli.runtime_provider import resolve_runtime_provider
    from run_agent import AIAgent
    try:
        from tools.terminal_tool import set_approval_callback
    except Exception:
        set_approval_callback = None
    try:
        from tools.approval import (
            register_gateway_notify,
            resolve_gateway_approval,
            set_current_session_key,
            reset_current_session_key,
            unregister_gateway_notify,
        )
    except Exception:
        register_gateway_notify = None
        resolve_gateway_approval = None
        set_current_session_key = None
        reset_current_session_key = None
        unregister_gateway_notify = None

    cfg = load_config() or {}
    model_cfg = cfg.get("model") or {}
    agent_cfg = cfg.get("agent") or {}
    provider_routing = cfg.get("provider_routing") or {}

    runtime = resolve_runtime_provider(
        requested=context.provider or model_cfg.get("provider") or "auto",
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

    def tool_progress(
        kind: str,
        tool_name: str | None = None,
        preview: str | None = None,
        args: Any | None = None,
        **_: Any,
    ) -> None:
        if kind not in {"tool.started", "tool.completed"}:
            return

        emit({
            "type": kind,
            "name": tool_name,
            "preview": preview,
            "input": args,
        })

    def status_callback(kind: str, message: str) -> None:
        if not message:
            return
        emit({
            "type": "agent.status",
            "kind": kind,
            "message": message,
        })

    def clarify_callback(question: str, choices: list[str] | None = None) -> str:
        choice_values = [str(choice) for choice in (choices or [])]
        prompt_choices = [
            WebChatPromptChoice(id=_choice_id(index), label=value, style="primary" if index == 0 else "neutral")
            for index, value in enumerate(choice_values)
        ]
        prompt = WebChatPrompt(
            id=uuid4().hex,
            runId=context.run_id,
            sessionId=context.session_id,
            kind="question",
            title="Question from Hermes",
            description=question,
            choices=prompt_choices,
            freeText=not prompt_choices,
            createdAt=_iso_now(),
        )
        answer = context.request_prompt(prompt, 600) if context.request_prompt else None
        if not answer:
            return "The user did not provide a response within the time limit. Use your best judgement and proceed."
        if prompt_choices:
            for index, value in enumerate(choice_values):
                if answer == _choice_id(index):
                    return value
        return str(answer)

    def approval_callback(command: str, description: str, *, allow_permanent: bool = True) -> str:
        choices = [
            WebChatPromptChoice(id="once", label="Allow once", style="primary"),
            WebChatPromptChoice(id="session", label="Allow this session", style="warning"),
        ]
        if allow_permanent:
            choices.append(WebChatPromptChoice(id="always", label="Always allow", style="warning"))
        choices.append(WebChatPromptChoice(id="deny", label="Deny", style="neutral"))
        prompt = WebChatPrompt(
            id=uuid4().hex,
            runId=context.run_id,
            sessionId=context.session_id,
            kind="approval",
            title="Allow command?",
            description=description or "Hermes wants to run a command that needs approval.",
            detail=command,
            detailType="command",
            choices=choices,
            createdAt=_iso_now(),
        )
        answer = context.request_prompt(prompt, 600) if context.request_prompt else None
        return answer if answer in {"once", "session", "always", "deny"} else "deny"

    def gateway_approval_notify(approval_data: dict[str, Any]) -> None:
        pattern_keys = approval_data.get("pattern_keys") or [approval_data.get("pattern_key")]
        allow_permanent = not any(str(key).startswith("tirith:") for key in pattern_keys if key)
        answer = approval_callback(
            str(approval_data.get("command") or ""),
            str(approval_data.get("description") or ""),
            allow_permanent=allow_permanent,
        )
        if resolve_gateway_approval:
            resolve_gateway_approval(context.session_id, answer or "deny")

    restore_approval_env = _set_web_approval_env(context.session_id)
    uninstall_approval_bridge = _install_terminal_approval_bridge(approval_callback)
    session_key_token = set_current_session_key(context.session_id) if set_current_session_key else None
    if register_gateway_notify:
        register_gateway_notify(context.session_id, gateway_approval_notify)
    if set_approval_callback:
        set_approval_callback(approval_callback)

    try:
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
            fallback_model=cfg.get("fallback_providers") or cfg.get("fallback_model") or None,
            providers_allowed=provider_routing.get("only"),
            providers_ignored=provider_routing.get("ignore"),
            providers_order=provider_routing.get("order"),
            provider_sort=provider_routing.get("sort"),
            reasoning_config=reasoning_config,
            stream_delta_callback=stream_delta,
            reasoning_callback=reasoning_delta,
            clarify_callback=clarify_callback,
            tool_progress_callback=tool_progress,
            status_callback=status_callback,
        )
        context.interrupt_agent = getattr(agent, "interrupt", None)
        context.steer_agent = getattr(agent, "steer", None)

        prompt = context.input
        if context.workspace:
            prompt = (
                f"Workspace: {context.workspace}. Use tool workdir/path arguments for file and terminal operations in this workspace.\n\n"
                f"{prompt}"
            )

        result = agent.run_conversation(
            prompt,
            conversation_history=conversation_history(context.session_id),
            task_id=context.run_id,
        )
        return str(result.get("final_response") or "")
    finally:
        if set_approval_callback:
            set_approval_callback(None)
        if unregister_gateway_notify:
            unregister_gateway_notify(context.session_id)
        if reset_current_session_key and session_key_token is not None:
            reset_current_session_key(session_key_token)
        uninstall_approval_bridge()
        restore_approval_env()


def conversation_history_for_agent(db_factory: Callable[[], Any], session_id: str) -> list[dict[str, str]]:
    messages = db_factory().get_messages(session_id)
    if messages and messages[-1].get("role") == "user":
        messages = messages[:-1]

    history: list[dict[str, str]] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role in {"system", "user", "assistant"} and isinstance(content, str) and content:
            history.append({"role": role, "content": content})
    return history
