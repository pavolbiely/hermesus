"""Model capability helpers for the web chat API."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .models import WebChatModelCapability

FALLBACK_CODEX_MODELS = [
    "gpt-5.5",
    "gpt-5.4-mini",
    "gpt-5.4",
    "gpt-5.3-codex",
    "gpt-5.2-codex",
    "gpt-5.1-codex-max",
    "gpt-5.1-codex-mini",
]


def resolve_codex_access_token() -> str | None:
    try:
        from hermes_cli.auth import resolve_codex_runtime_credentials

        creds = resolve_codex_runtime_credentials(refresh_if_expiring=True)
    except Exception:
        return None

    token = creds.get("api_key") if isinstance(creds, dict) else None
    return token.strip() if isinstance(token, str) and token.strip() else None


def available_model_ids(resolve_access_token: Callable[[], str | None] = resolve_codex_access_token) -> list[str]:
    try:
        from hermes_cli.codex_models import DEFAULT_CODEX_MODELS, get_codex_model_ids

        model_ids = get_codex_model_ids(access_token=resolve_access_token())
        return [model_id for model_id in model_ids if model_id] or list(DEFAULT_CODEX_MODELS)
    except Exception:
        return list(FALLBACK_CODEX_MODELS)


def model_reasoning_efforts(model_id: str | None) -> list[str]:
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


def default_reasoning_effort(model_id: str | None) -> str | None:
    normalized = str(model_id or "").strip().lower()
    efforts = model_reasoning_efforts(normalized)
    if normalized in {"gpt-5-pro", "gpt-5.4-pro"}:
        return "high"
    if normalized.startswith("gpt-5.4") or normalized.startswith("gpt-5.1"):
        return "none" if "none" in efforts else "medium"
    if "medium" in efforts:
        return "medium"
    return efforts[0] if efforts else None


def model_capabilities(available_ids: Callable[[], list[str]] = available_model_ids) -> list[WebChatModelCapability]:
    capabilities: list[WebChatModelCapability] = []
    for model_id in available_ids():
        capabilities.append(
            WebChatModelCapability(
                id=model_id,
                label=model_id,
                reasoningEfforts=model_reasoning_efforts(model_id),
                defaultReasoningEffort=default_reasoning_effort(model_id),
            )
        )
    return capabilities


def default_model_id(available_ids: Callable[[], list[str]] = available_model_ids) -> str | None:
    model_ids = available_ids()
    return model_ids[0] if model_ids else None


def resolve_requested_model(
    model_id: str | None,
    *,
    session: dict[str, Any] | None = None,
    default_model: Callable[[], str | None] = default_model_id,
) -> str | None:
    requested = str(model_id or "").strip()
    if requested:
        return requested
    session_model = str((session or {}).get("model") or "").strip()
    if session_model:
        return session_model
    return default_model()


def resolve_requested_reasoning_effort(
    model_id: str | None,
    reasoning_effort: str | None,
    *,
    session: dict[str, Any] | None = None,
    session_reasoning_effort: Callable[[dict[str, Any] | None], str | None],
) -> str | None:
    supported = model_reasoning_efforts(model_id)
    requested = str(reasoning_effort or "").strip().lower()
    if requested in supported:
        return requested

    session_reasoning = session_reasoning_effort(session)
    if session_reasoning in supported:
        return session_reasoning

    default_effort = default_reasoning_effort(model_id)
    if default_effort in supported:
        return default_effort

    if "medium" in supported:
        return "medium"
    return supported[0] if supported else None
