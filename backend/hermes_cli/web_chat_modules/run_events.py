"""Pure helpers for web-chat run events and persisted event parts."""

from __future__ import annotations

import json
from typing import Any

MESSAGE_ITEMS_FIELD = "codex_message_items"


def client_message_id_from_message(message: dict[str, Any]) -> str | None:
    items = message.get(MESSAGE_ITEMS_FIELD)
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


def task_plan_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("type") != "task_plan.updated":
        return None

    task_plan = event.get("taskPlan")
    if isinstance(task_plan, dict) and isinstance(task_plan.get("items"), list):
        return task_plan
    return None


def system_event_part(event: dict[str, Any], occurred_at: str) -> dict[str, Any] | None:
    event_type = event.get("type")

    if event_type == "run.steered":
        return {
            "eventType": "run_steered",
            "severity": "info",
            "title": "Run steered",
            "description": event.get("text") if isinstance(event.get("text"), str) else None,
            "occurredAt": occurred_at,
        }
    if event_type == "run.stopped":
        return {
            "eventType": "run_stopped",
            "severity": "info",
            "title": "Run stopped",
            "description": event.get("message") if isinstance(event.get("message"), str) else "Stopped by user.",
            "occurredAt": occurred_at,
        }
    if event_type == "run.failed":
        return {
            "eventType": "run_failed",
            "severity": "error",
            "title": "Run failed",
            "description": event.get("error") if isinstance(event.get("error"), str) else None,
            "occurredAt": occurred_at,
        }
    if event_type == "run.interrupted":
        return {
            "eventType": "run_interrupted",
            "severity": "warning",
            "title": "Run interrupted",
            "description": event.get("message") if isinstance(event.get("message"), str) else None,
            "occurredAt": occurred_at,
        }
    if event_type == "agent.status" and event.get("kind") == "warn":
        return {
            "eventType": "agent_warning",
            "severity": "warning",
            "title": "Agent warning",
            "description": event.get("message") if isinstance(event.get("message"), str) else None,
            "occurredAt": occurred_at,
        }
    if event_type in {"prompt.expired", "prompt.cancelled"}:
        prompt = event.get("prompt")
        if not isinstance(prompt, dict):
            return None

        prompt_kind = prompt.get("kind")
        prompt_title = prompt.get("title") if isinstance(prompt.get("title"), str) else None
        is_approval = prompt_kind == "approval"
        return {
            "eventType": "prompt_expired" if event_type == "prompt.expired" else "prompt_cancelled",
            "severity": "warning",
            "title": (
                "Approval expired" if is_approval and event_type == "prompt.expired"
                else "Question expired" if event_type == "prompt.expired"
                else "Approval cancelled" if is_approval
                else "Question cancelled"
            ),
            "description": prompt_title,
            "occurredAt": occurred_at,
            "metadata": {"promptId": prompt.get("id")},
        }
    return None
