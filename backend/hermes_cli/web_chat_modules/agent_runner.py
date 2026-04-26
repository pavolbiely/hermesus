"""Hermes Agent execution helpers for the native web chat API."""

from __future__ import annotations

from typing import Any, Callable

from .run_manager import RunContext

WEB_CHAT_SOURCE = "web-chat"


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
    context.interrupt_agent = getattr(agent, "interrupt", None)

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
