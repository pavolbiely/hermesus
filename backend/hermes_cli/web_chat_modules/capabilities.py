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


def runtime_provider(requested: str | None = None, target_model: str | None = None) -> dict[str, Any]:
    try:
        from hermes_cli.config import load_config
        from hermes_cli.runtime_provider import resolve_runtime_provider

        cfg = load_config() or {}
        model_cfg = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
        return resolve_runtime_provider(
            requested=requested or model_cfg.get("provider") or "auto",
            target_model=target_model,
        )
    except Exception:
        return {}


def active_provider_id() -> str:
    provider = runtime_provider().get("provider")
    return str(provider or "auto")


def _configured_model_id() -> str | None:
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        model_cfg = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
        model = model_cfg.get("default") or model_cfg.get("model")
        return str(model).strip() if model else None
    except Exception:
        return None


def _dedupe_model_ids(model_ids: list[str], preferred: str | None = None) -> list[str]:
    ordered = [preferred, *model_ids] if preferred else model_ids
    seen: set[str] = set()
    result: list[str] = []
    for model_id in ordered:
        value = str(model_id or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def available_model_ids(resolve_access_token: Callable[[], str | None] = resolve_codex_access_token) -> list[str]:
    configured_model = _configured_model_id()
    runtime = runtime_provider(target_model=configured_model)
    provider = str(runtime.get("provider") or "").strip().lower()

    if provider == "openai-codex" or (not provider and configured_model and configured_model.startswith("gpt-5")):
        try:
            from hermes_cli.codex_models import DEFAULT_CODEX_MODELS, get_codex_model_ids

            model_ids = get_codex_model_ids(access_token=resolve_access_token())
            return _dedupe_model_ids(model_ids or list(DEFAULT_CODEX_MODELS), preferred=configured_model)
        except Exception:
            return _dedupe_model_ids(list(FALLBACK_CODEX_MODELS), preferred=configured_model)

    base_url = str(runtime.get("base_url") or "").strip()
    api_key = str(runtime.get("api_key") or "").strip()
    api_mode = str(runtime.get("api_mode") or "").strip() or None
    if base_url:
        try:
            from hermes_cli.models import fetch_api_models

            model_ids = fetch_api_models(api_key, base_url, timeout=5.0, api_mode=api_mode)
            if model_ids:
                return _dedupe_model_ids(model_ids, preferred=configured_model)
        except Exception:
            pass

    if configured_model:
        return [configured_model]
    return []


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


def model_context_window_tokens(model_id: str | None) -> int | None:
    model = str(model_id or "").strip()
    if not model:
        return None

    try:
        from agent.model_metadata import get_model_context_length
        from hermes_cli.config import get_compatible_custom_providers, load_config

        cfg = load_config() or {}
        model_cfg = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
        raw_context_length = model_cfg.get("context_length")
        config_context_length = int(raw_context_length) if raw_context_length else None
        runtime = runtime_provider(target_model=model)
        context_length = get_model_context_length(
            model,
            base_url=str(runtime.get("base_url") or ""),
            api_key=str(runtime.get("api_key") or ""),
            config_context_length=config_context_length,
            provider=str(runtime.get("provider") or ""),
            custom_providers=get_compatible_custom_providers(cfg),
        )
        return int(context_length) if context_length and context_length > 0 else None
    except Exception:
        return None


def _compression_threshold() -> float | None:
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        compression_cfg = cfg.get("compression") if isinstance(cfg.get("compression"), dict) else {}
        enabled = str(compression_cfg.get("enabled", True)).lower() in {"true", "1", "yes"}
        if not enabled:
            return None
        threshold = float(compression_cfg.get("threshold", 0.50))
        return min(1.0, max(0.0, threshold))
    except Exception:
        return 0.50


def model_auto_compress_tokens(model_id: str | None) -> int | None:
    context_window_tokens = model_context_window_tokens(model_id)
    threshold = _compression_threshold()
    if context_window_tokens is None or threshold is None:
        return None
    return round(context_window_tokens * threshold)


def model_capabilities(available_ids: Callable[[], list[str]] = available_model_ids) -> list[WebChatModelCapability]:
    capabilities: list[WebChatModelCapability] = []
    compression_threshold = _compression_threshold()
    for model_id in available_ids():
        context_window_tokens = model_context_window_tokens(model_id)
        auto_compress_tokens = (
            round(context_window_tokens * compression_threshold)
            if context_window_tokens and compression_threshold is not None
            else None
        )
        capabilities.append(
            WebChatModelCapability(
                id=model_id,
                label=model_id,
                reasoningEfforts=model_reasoning_efforts(model_id),
                defaultReasoningEffort=default_reasoning_effort(model_id),
                contextWindowTokens=context_window_tokens,
                autoCompressTokens=auto_compress_tokens,
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
