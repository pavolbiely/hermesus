"""Durable run-event log and crash recovery helpers for web chat."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from .run_events import system_event_part, task_plan_from_event

TERMINAL_EVENT_TYPES = {"run.completed", "run.stopped", "run.failed", "run.interrupted"}
_SCHEMA_READY_DB_PATHS: set[str] = set()


def ensure_run_event_log_schema(db: Any) -> None:
    if not hasattr(db, "_execute_write"):
        return
    db_path = str(getattr(db, "db_path", "")) or str(id(db))
    if db_path in _SCHEMA_READY_DB_PATHS:
        return

    def _do(conn: Any) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS web_chat_run_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                event_index INTEGER NOT NULL,
                type TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at REAL NOT NULL,
                terminal INTEGER NOT NULL DEFAULT 0,
                recovered_at REAL
            )
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_web_chat_run_events_run_event_index
            ON web_chat_run_events(run_id, event_index)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_web_chat_run_events_session_run
            ON web_chat_run_events(session_id, run_id, id)
            """
        )

    db._execute_write(_do)
    _SCHEMA_READY_DB_PATHS.add(db_path)


def record_run_event(db: Any, event: dict[str, Any]) -> None:
    run_id = event.get("runId")
    session_id = event.get("sessionId")
    event_index = event.get("id")
    event_type = event.get("type")
    if not isinstance(run_id, str) or not isinstance(session_id, str) or not isinstance(event_type, str):
        return
    if not isinstance(event_index, int):
        return

    ensure_run_event_log_schema(db)
    if not hasattr(db, "_execute_write"):
        return
    payload = json.dumps(event, separators=(",", ":"), sort_keys=True)
    created_at = _event_created_at(event)
    terminal = 1 if event_type in TERMINAL_EVENT_TYPES else 0

    def _do(conn: Any) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO web_chat_run_events
                (run_id, session_id, event_index, type, payload, created_at, terminal)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, session_id, event_index, event_type, payload, created_at, terminal),
        )

    db._execute_write(_do)


def recover_interrupted_run_for_session(db: Any, session_id: str) -> None:
    """Persist a partial assistant response for a run lost across backend restart."""
    ensure_run_event_log_schema(db)
    run_id = _latest_unfinished_run_id(db, session_id)
    if not run_id:
        return

    events = _events_for_run(db, run_id)
    if not events:
        return

    assistant = assistant_recovery_from_events(events)
    interrupted_at = datetime.now(timezone.utc).isoformat()
    appended_message = False
    if assistant["content"] or assistant["reasoning"] or assistant["parts"]:
        db.append_message(
            session_id,
            "assistant",
            assistant["content"] or None,
            reasoning=assistant["reasoning"] or None,
            codex_message_items=(
                [{"type": "web_chat_recovered_parts", "parts": assistant["parts"]}]
                if assistant["parts"]
                else None
            ),
        )
        appended_message = True

    event = {
        "id": _next_event_index(db, run_id),
        "type": "run.interrupted",
        "runId": run_id,
        "sessionId": session_id,
        "message": "Backend restarted while this run was in progress. Partial response was restored." if appended_message else "Backend restarted while this run was in progress.",
        "occurredAt": interrupted_at,
    }
    system_event = system_event_part(event, interrupted_at)
    if system_event:
        db.append_message(
            session_id,
            "system",
            None,
            codex_message_items=[{"type": "web_chat_event", "event": system_event}],
        )

    record_run_event(db, event)
    _mark_run_recovered(db, run_id)


def assistant_recovery_from_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    content_chunks: list[str] = []
    reasoning_chunks: list[str] = []
    parts: list[dict[str, Any]] = []
    latest_task_plan: dict[str, Any] | None = None

    for event in events:
        event_type = event.get("type")
        if event_type == "message.delta" and isinstance(event.get("content"), str):
            content_chunks.append(event["content"])
            continue
        if event_type == "reasoning.delta" and isinstance(event.get("content"), str):
            reasoning_chunks.append(event["content"])
            continue
        if event_type == "agent.status" and isinstance(event.get("message"), str):
            parts.append({
                "type": "status",
                "text": event["message"],
                "status": event.get("kind") if isinstance(event.get("kind"), str) else None,
                "startedAt": event.get("createdAt") if isinstance(event.get("createdAt"), str) else None,
            })
            continue
        if event_type == "prompt.requested" and isinstance(event.get("prompt"), dict):
            parts.append({"type": "interactive_prompt", "prompt": event["prompt"]})
            continue
        if event_type == "tool.started":
            parts.append(_tool_started_part(event))
            continue
        if event_type == "tool.completed":
            _complete_latest_tool_part(parts, event)
            continue
        task_plan = task_plan_from_event(event)
        if task_plan is not None:
            latest_task_plan = _finalized_task_plan(task_plan)

    if latest_task_plan:
        parts.append({"type": "task_plan", "taskPlan": latest_task_plan})

    return {
        "content": "".join(content_chunks).strip(),
        "reasoning": "".join(reasoning_chunks).strip(),
        "parts": [part for part in parts if _is_useful_part(part)],
    }


def _tool_started_part(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "tool",
        "name": event.get("name") if isinstance(event.get("name"), str) else None,
        "status": "running",
        "startedAt": event.get("occurredAt") if isinstance(event.get("occurredAt"), str) else None,
        "input": event.get("input", event.get("preview")),
    }


def _complete_latest_tool_part(parts: list[dict[str, Any]], event: dict[str, Any]) -> None:
    name = event.get("name") if isinstance(event.get("name"), str) else None
    for part in reversed(parts):
        if part.get("type") != "tool" or part.get("status") == "completed":
            continue
        if name and part.get("name") and part.get("name") != name:
            continue
        part["status"] = "completed"
        part["completedAt"] = event.get("occurredAt") if isinstance(event.get("occurredAt"), str) else None
        part["durationMs"] = event.get("durationMs") if isinstance(event.get("durationMs"), (int, float)) else None
        part["output"] = event.get("output")
        return

    part = _tool_started_part(event)
    part["status"] = "completed"
    part["completedAt"] = event.get("occurredAt") if isinstance(event.get("occurredAt"), str) else None
    part["output"] = event.get("output")
    parts.append(part)


def _finalized_task_plan(task_plan: dict[str, Any]) -> dict[str, Any]:
    items = []
    for item in task_plan.get("items", []):
        if not isinstance(item, dict):
            continue
        next_item = dict(item)
        if next_item.get("status") == "in_progress":
            next_item["status"] = "cancelled"
        items.append(next_item)
    return {**task_plan, "items": items}


def _is_useful_part(part: dict[str, Any]) -> bool:
    part_type = part.get("type")
    if part_type == "status":
        return bool(part.get("text"))
    if part_type == "task_plan":
        return bool(isinstance(part.get("taskPlan"), dict) and part["taskPlan"].get("items"))
    return True


def _latest_unfinished_run_id(db: Any, session_id: str) -> str | None:
    with db._lock:
        rows = db._conn.execute(
            """
            SELECT candidate.run_id,
                   MAX(candidate.id) AS last_id,
                   MAX(candidate.recovered_at) AS recovered_at
            FROM web_chat_run_events AS candidate
            WHERE candidate.session_id = ?
              AND NOT EXISTS (
                SELECT 1
                FROM web_chat_run_events AS terminal
                WHERE terminal.run_id = candidate.run_id
                  AND terminal.terminal = 1
              )
            GROUP BY candidate.run_id
            HAVING recovered_at IS NULL
            ORDER BY last_id DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchall()
    if not rows:
        return None
    return str(rows[0]["run_id"])


def _events_for_run(db: Any, run_id: str) -> list[dict[str, Any]]:
    with db._lock:
        rows = db._conn.execute(
            """
            SELECT payload
            FROM web_chat_run_events
            WHERE run_id = ?
            ORDER BY event_index, id
            """,
            (run_id,),
        ).fetchall()
    events: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _next_event_index(db: Any, run_id: str) -> int:
    with db._lock:
        row = db._conn.execute(
            "SELECT COALESCE(MAX(event_index), 0) + 1 AS next_index FROM web_chat_run_events WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    return int(row["next_index"] if row else 1)


def _mark_run_recovered(db: Any, run_id: str) -> None:
    recovered_at = time.time()

    def _do(conn: Any) -> None:
        conn.execute("UPDATE web_chat_run_events SET recovered_at = ? WHERE run_id = ?", (recovered_at, run_id))

    db._execute_write(_do)


def _event_created_at(event: dict[str, Any]) -> float:
    for key in ("occurredAt", "createdAt"):
        value = event.get(key)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                pass
    return time.time()
