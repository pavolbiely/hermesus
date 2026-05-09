"""Provider usage and rate-limit helpers for the web chat API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import requests

from .capabilities import resolve_codex_access_token, runtime_provider
from .models import WebChatProviderUsageLimit, WebChatProviderUsageResponse, WebChatProviderUsageWindow

CODEX_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"


def _window_label(window_minutes: int | None, fallback: str) -> str:
    if window_minutes is None:
        return fallback
    if window_minutes >= 60 * 24 * 6:
        return "Weekly"
    if window_minutes >= 60 * 18:
        return "Daily"
    if window_minutes >= 60:
        hours = round(window_minutes / 60)
        return f"{hours}h"
    return f"{window_minutes}m"


def _parse_reset_timestamp(value: Any) -> str | None:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    except Exception:
        return None


def _parse_codex_window(raw: dict[str, Any] | None, fallback_label: str) -> WebChatProviderUsageWindow | None:
    if not isinstance(raw, dict):
        return None
    used_percent = raw.get("used_percent")
    if not isinstance(used_percent, (int, float)):
        return None
    window_seconds = raw.get("limit_window_seconds")
    window_minutes = round(window_seconds / 60) if isinstance(window_seconds, (int, float)) and window_seconds > 0 else None
    used = min(100.0, max(0.0, float(used_percent)))
    return WebChatProviderUsageWindow(
        label=_window_label(window_minutes, fallback_label),
        usedPercent=round(used, 1),
        remainingPercent=round(max(0.0, 100.0 - used), 1),
        windowMinutes=window_minutes,
        resetsAt=_parse_reset_timestamp(raw.get("reset_at")),
    )


def _parse_codex_limit(limit_id: str, limit_name: str | None, raw: dict[str, Any] | None) -> WebChatProviderUsageLimit:
    windows: list[WebChatProviderUsageWindow] = []
    if isinstance(raw, dict):
        primary = _parse_codex_window(raw.get("primary_window"), "Primary")
        secondary = _parse_codex_window(raw.get("secondary_window"), "Secondary")
        windows = [window for window in (primary, secondary) if window]
    return WebChatProviderUsageLimit(
        id=limit_id,
        label=limit_name or limit_id,
        windows=windows,
    )


def _codex_headers(access_token: str) -> dict[str, str]:
    try:
        from agent.auxiliary_client import _codex_cloudflare_headers

        headers = _codex_cloudflare_headers(access_token)
    except Exception:
        headers = {"Authorization": f"Bearer {access_token}"}
    headers.setdefault("Authorization", f"Bearer {access_token}")
    headers.setdefault("User-Agent", "codex_cli_rs/0.0.0")
    return headers


def codex_provider_usage(
    *,
    resolve_access_token: Callable[[], str | None] = resolve_codex_access_token,
    request_get: Callable[..., Any] = requests.get,
    access_token: str | None = None,
) -> WebChatProviderUsageResponse:
    resolved_access_token = access_token or resolve_access_token()
    if not resolved_access_token:
        return WebChatProviderUsageResponse(
            provider="openai-codex",
            source="codex",
            available=False,
            unavailableReason="Codex authentication is not available.",
            limits=[],
        )

    try:
        response = request_get(CODEX_USAGE_URL, headers=_codex_headers(resolved_access_token), timeout=10)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return WebChatProviderUsageResponse(
            provider="openai-codex",
            source="codex",
            available=False,
            unavailableReason=f"Could not fetch Codex usage: {exc}",
            limits=[],
        )

    if not isinstance(payload, dict):
        return WebChatProviderUsageResponse(
            provider="openai-codex",
            source="codex",
            available=False,
            unavailableReason="Codex usage response was not an object.",
            limits=[],
        )

    limits = [_parse_codex_limit("codex", None, payload.get("rate_limit"))]
    additional = payload.get("additional_rate_limits")
    if isinstance(additional, list):
        for item in additional:
            if not isinstance(item, dict):
                continue
            limit_id = str(item.get("metered_feature") or item.get("limit_name") or "").strip()
            if not limit_id:
                continue
            limit_name = item.get("limit_name") if isinstance(item.get("limit_name"), str) else None
            limits.append(_parse_codex_limit(limit_id, limit_name, item.get("rate_limit")))

    return WebChatProviderUsageResponse(
        provider="openai-codex",
        source="codex",
        available=any(limit.windows for limit in limits),
        unavailableReason=None if any(limit.windows for limit in limits) else "Codex did not return rate-limit windows.",
        limits=limits,
        capturedAt=datetime.now(timezone.utc).isoformat(),
    )


def provider_usage(
    provider: str | None = None,
    model: str | None = None,
    *,
    codex_usage: Callable[[], WebChatProviderUsageResponse] = codex_provider_usage,
    request_get: Callable[..., Any] = requests.get,
) -> WebChatProviderUsageResponse:
    requested = str(provider or "").strip() or None
    runtime = runtime_provider(requested=requested, target_model=model)
    resolved_provider = str(runtime.get("provider") or requested or "auto").strip()
    normalized = resolved_provider.lower()

    if normalized == "openai-codex":
        runtime_access_token = runtime.get("api_key") if isinstance(runtime.get("api_key"), str) else None
        if codex_usage is codex_provider_usage:
            usage = codex_provider_usage(access_token=runtime_access_token, request_get=request_get)
        else:
            usage = codex_usage()
        usage.provider = resolved_provider
        usage.model = model
        return usage

    return WebChatProviderUsageResponse(
        provider=resolved_provider,
        model=model,
        source=normalized or "auto",
        available=False,
        unavailableReason="Provider usage is not available for this provider yet.",
        limits=[],
        capturedAt=datetime.now(timezone.utc).isoformat(),
    )
