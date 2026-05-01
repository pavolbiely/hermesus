"""Runtime ETA estimation and calibration for web-chat runs."""

from __future__ import annotations

import re
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Iterable

from hermes_state import SessionDB

from .models import WebChatRunEta

DEFAULT_SLICE_MS = 10 * 60 * 1000
RETENTION_PER_BUCKET = 200
RETENTION_TOTAL = 2000
_DONE_STATUSES = {"completed", "cancelled"}
_VALIDATION_ORDER = ("tests", "typecheck", "build", "browser_qa")


@dataclass(frozen=True)
class WebChatEtaClassification:
    task_type: str = "unknown"
    project_area: str = "unknown"
    validation_profile: str = "none"


def ensure_eta_schema(db: SessionDB) -> None:
    def _do(conn: Any) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS web_chat_eta_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                profile TEXT,
                workspace TEXT,
                provider TEXT,
                model TEXT,
                reasoning_effort TEXT,
                max_turns INTEGER,
                task_type TEXT NOT NULL DEFAULT 'unknown',
                project_area TEXT NOT NULL DEFAULT 'unknown',
                validation_profile TEXT NOT NULL DEFAULT 'unknown',
                task_count INTEGER NOT NULL,
                completed_task_count INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                active_duration_ms INTEGER NOT NULL,
                tool_duration_ms INTEGER NOT NULL DEFAULT 0,
                prompt_wait_duration_ms INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_web_chat_eta_samples_lookup
            ON web_chat_eta_samples(
                profile, workspace, provider, model, max_turns,
                task_type, project_area, validation_profile, created_at DESC
            )
            """
        )

    db._execute_write(_do)


def task_items(task_plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    items = task_plan.get("items") if isinstance(task_plan, dict) else None
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def total_task_count(task_plan: dict[str, Any] | None) -> int:
    return len(task_items(task_plan))


def completed_task_count(task_plan: dict[str, Any] | None) -> int:
    return sum(1 for item in task_items(task_plan) if item.get("status") in _DONE_STATUSES)


def remaining_task_weight(task_plan: dict[str, Any] | None) -> float:
    remaining = 0.0
    for item in task_items(task_plan):
        status = item.get("status")
        if status in _DONE_STATUSES:
            continue
        remaining += 0.5 if status == "in_progress" else 1.0
    return remaining


def classify_task(
    context: Any,
    task_plan: dict[str, Any] | None,
    workspace_changes: Any | None = None,
    observed_commands: Iterable[str] | None = None,
) -> WebChatEtaClassification:
    text = " ".join(
        value for value in [getattr(context, "input", None), _task_plan_text(task_plan)]
        if isinstance(value, str)
    ).lower()
    return WebChatEtaClassification(
        task_type=_classify_task_type(text),
        project_area=_classify_project_area(workspace_changes, text),
        validation_profile=_classify_validation_profile(observed_commands),
    )


def record_eta_sample(
    db: SessionDB,
    context: Any,
    latest_task_plan: dict[str, Any] | None,
    *,
    duration_ms: int,
    tool_duration_ms: int = 0,
    prompt_wait_duration_ms: int = 0,
    status: str = "completed",
    workspace_changes: Any | None = None,
    observed_commands: Iterable[str] | None = None,
) -> None:
    task_count = total_task_count(latest_task_plan)
    if task_count <= 0:
        return

    ensure_eta_schema(db)
    classification = classify_task(context, latest_task_plan, workspace_changes, observed_commands)
    active_duration_ms = max(0, int(duration_ms) - max(0, int(prompt_wait_duration_ms)))
    values = (
        time.time(),
        getattr(context, "profile", None),
        getattr(context, "workspace", None),
        getattr(context, "provider", None),
        getattr(context, "model", None),
        getattr(context, "reasoning_effort", None),
        getattr(context, "max_turns", None),
        classification.task_type,
        classification.project_area,
        classification.validation_profile,
        task_count,
        completed_task_count(latest_task_plan),
        int(duration_ms),
        active_duration_ms,
        max(0, int(tool_duration_ms)),
        max(0, int(prompt_wait_duration_ms)),
        status,
    )

    def _do(conn: Any) -> None:
        conn.execute(
            """
            INSERT INTO web_chat_eta_samples (
                created_at, profile, workspace, provider, model, reasoning_effort, max_turns,
                task_type, project_area, validation_profile,
                task_count, completed_task_count, duration_ms, active_duration_ms,
                tool_duration_ms, prompt_wait_duration_ms, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        conn.execute(
            """
            DELETE FROM web_chat_eta_samples
            WHERE id IN (
                SELECT id FROM web_chat_eta_samples
                WHERE profile IS ? AND workspace IS ? AND provider IS ? AND model IS ? AND max_turns IS ?
                  AND task_type = ? AND project_area = ? AND validation_profile = ? AND status = 'completed'
                ORDER BY created_at DESC
                LIMIT -1 OFFSET ?
            )
            """,
            (
                getattr(context, "profile", None),
                getattr(context, "workspace", None),
                getattr(context, "provider", None),
                getattr(context, "model", None),
                getattr(context, "max_turns", None),
                classification.task_type,
                classification.project_area,
                classification.validation_profile,
                RETENTION_PER_BUCKET,
            ),
        )
        conn.execute(
            """
            DELETE FROM web_chat_eta_samples
            WHERE id IN (
                SELECT id FROM web_chat_eta_samples
                ORDER BY created_at DESC
                LIMIT -1 OFFSET ?
            )
            """,
            (RETENTION_TOTAL,),
        )

    db._execute_write(_do)


def estimate_run_eta(
    db: SessionDB,
    context: Any,
    task_plan: dict[str, Any] | None,
    *,
    started_at: float,
    now: float | None = None,
    observed_commands: Iterable[str] | None = None,
) -> WebChatRunEta | None:
    total = total_task_count(task_plan)
    if total <= 0:
        return None

    now = now or time.time()
    completed = completed_task_count(task_plan)
    remaining_weight = remaining_task_weight(task_plan)
    if remaining_weight <= 0:
        return None

    ensure_eta_schema(db)
    classification = classify_task(context, task_plan, observed_commands=observed_commands)
    lookup = _calibrated_slice_ms(db, context, classification)
    slice_ms = lookup[0] if lookup else DEFAULT_SLICE_MS
    basis = lookup[1] if lookup else "default"
    sample_count = lookup[2] if lookup else 0

    elapsed_ms = max(0, round((now - started_at) * 1000))
    if completed > 0 and elapsed_ms >= 60_000:
        observed_slice_ms = max(1, round(elapsed_ms / completed))
        slice_ms = round((0.65 * slice_ms) + (0.35 * observed_slice_ms))
        basis = "observed" if basis == "default" else basis

    remaining_ms = max(1, round(remaining_weight * slice_ms))
    confidence = "high" if sample_count >= 5 and basis in {"validation_profile", "project_area", "task_type"} else "medium" if sample_count >= 3 else "low"
    updated_at = _iso_from_epoch(now)
    return WebChatRunEta(
        remainingMs=remaining_ms,
        estimatedCompletionAt=_iso_from_epoch(now + (remaining_ms / 1000)),
        confidence=confidence,
        basis=basis,
        taskType=classification.task_type,
        projectArea=classification.project_area,
        validationProfile=classification.validation_profile,
        totalSlices=total,
        completedSlices=completed,
        sliceMs=slice_ms,
        updatedAt=updated_at,
    )


def _calibrated_slice_ms(db: SessionDB, context: Any, classification: WebChatEtaClassification) -> tuple[int, str, int] | None:
    profile = getattr(context, "profile", None)
    workspace = getattr(context, "workspace", None)
    provider = getattr(context, "provider", None)
    model = getattr(context, "model", None)
    max_turns = getattr(context, "max_turns", None)
    queries = [
        (
            """
            SELECT active_duration_ms, task_count FROM web_chat_eta_samples
            WHERE status = 'completed' AND profile IS ? AND workspace IS ? AND provider IS ? AND model IS ? AND max_turns IS ?
              AND task_type = ? AND project_area = ? AND validation_profile = ?
            ORDER BY created_at DESC LIMIT 20
            """,
            (profile, workspace, provider, model, max_turns, classification.task_type, classification.project_area, classification.validation_profile),
            "validation_profile",
        ),
        (
            """
            SELECT active_duration_ms, task_count FROM web_chat_eta_samples
            WHERE status = 'completed' AND profile IS ? AND workspace IS ? AND provider IS ? AND model IS ? AND max_turns IS ?
              AND task_type = ? AND project_area = ?
            ORDER BY created_at DESC LIMIT 20
            """,
            (profile, workspace, provider, model, max_turns, classification.task_type, classification.project_area),
            "project_area",
        ),
        (
            """
            SELECT active_duration_ms, task_count FROM web_chat_eta_samples
            WHERE status = 'completed' AND profile IS ? AND workspace IS ? AND provider IS ? AND model IS ? AND max_turns IS ?
              AND task_type = ?
            ORDER BY created_at DESC LIMIT 20
            """,
            (profile, workspace, provider, model, max_turns, classification.task_type),
            "task_type",
        ),
        (
            """
            SELECT active_duration_ms, task_count FROM web_chat_eta_samples
            WHERE status = 'completed' AND profile IS ? AND workspace IS ? AND provider IS ? AND model IS ? AND max_turns IS ?
            ORDER BY created_at DESC LIMIT 20
            """,
            (profile, workspace, provider, model, max_turns),
            "workspace_model",
        ),
        (
            """
            SELECT active_duration_ms, task_count FROM web_chat_eta_samples
            WHERE status = 'completed' AND profile IS ? AND workspace IS ? AND max_turns IS ?
            ORDER BY created_at DESC LIMIT 20
            """,
            (profile, workspace, max_turns),
            "workspace",
        ),
        (
            """
            SELECT active_duration_ms, task_count FROM web_chat_eta_samples
            WHERE status = 'completed' AND profile IS ? AND max_turns IS ?
            ORDER BY created_at DESC LIMIT 20
            """,
            (profile, max_turns),
            "profile",
        ),
    ]

    with db._lock:
        for sql, params, basis in queries:
            rows = db._conn.execute(sql, params).fetchall()
            slice_values = [max(1, row["active_duration_ms"] // max(1, row["task_count"])) for row in rows]
            if slice_values:
                return round(statistics.median(slice_values)), basis, len(slice_values)
    return None


def _task_plan_text(task_plan: dict[str, Any] | None) -> str:
    return " ".join(str(item.get("content") or "") for item in task_items(task_plan))


def _classify_task_type(text: str) -> str:
    checks = [
        ("test", r"\b(test|tests|pytest|vitest|coverage)\b"),
        ("refactor", r"\b(refactor|cleanup|extract|rename|split|migrate)\b"),
        ("bugfix", r"\b(fix|bug|regression|broken|error|crash|issue)\b"),
        ("ui", r"\b(ui|visual|layout|modal|sidebar|button|css|style|polish)\b"),
        ("docs", r"\b(docs?|readme|documentation|copy)\b"),
        ("research", r"\b(research|investigate|inspect|explore|spike)\b"),
        ("maintenance", r"\b(update|upgrade|chore|maintenance|dependency)\b"),
        ("feature", r"\b(add|implement|create|support|enable|feature)\b"),
    ]
    for task_type, pattern in checks:
        if re.search(pattern, text):
            return task_type
    return "unknown"


def _classify_project_area(workspace_changes: Any | None, fallback_text: str) -> str:
    paths = _change_paths(workspace_changes)
    areas = {_area_for_path(path) for path in paths}
    areas.discard("unknown")
    if len(areas) > 1:
        return "multi_area"
    if len(areas) == 1:
        return next(iter(areas))

    text = fallback_text.lower()
    text_checks = [
        ("frontend", ("frontend", "vue", "nuxt", "web/app", "ui", "css")),
        ("backend", ("backend", "api", "fastapi", "python", "run manager")),
        ("database", ("database", "sqlite", "sql", "schema", "migration")),
        ("tests", ("test", "pytest", "vitest")),
        ("docs", ("docs", "readme", "documentation")),
        ("config", ("config", "settings", "env")),
    ]
    for area, markers in text_checks:
        if any(marker in text for marker in markers):
            return area
    return "unknown"


def _change_paths(workspace_changes: Any | None) -> list[str]:
    if workspace_changes is None:
        return []
    if hasattr(workspace_changes, "model_dump"):
        workspace_changes = workspace_changes.model_dump()
    files = workspace_changes.get("files") if isinstance(workspace_changes, dict) else workspace_changes
    if not isinstance(files, list):
        return []
    paths: list[str] = []
    for file in files:
        if isinstance(file, dict) and isinstance(file.get("path"), str):
            paths.append(file["path"])
        elif hasattr(file, "path"):
            paths.append(str(file.path))
    return paths


def _area_for_path(path: str) -> str:
    normalized = PurePosixPath(path.replace("\\", "/"))
    parts = normalized.parts
    if any(part in {"tests", "test", "__tests__"} for part in parts) or normalized.name.endswith(('.test.ts', '.test.mjs', '_test.py')):
        return "tests"
    if parts[:2] == ("web", "app") or parts[:2] == ("apps", "platform") or normalized.suffix in {".vue", ".css"}:
        return "frontend"
    if parts and parts[0] == "backend" or normalized.suffix == ".py":
        return "backend"
    if parts and parts[0] in {"database", "migrations"} or normalized.suffix == ".sql":
        return "database"
    if parts and parts[0] == "docs" or normalized.name.lower() in {"readme.md", "agents.md"}:
        return "docs"
    if normalized.name in {"package.json", "pnpm-lock.yaml", "nuxt.config.ts", "tsconfig.json"} or normalized.suffix in {".json", ".yaml", ".yml", ".toml"}:
        return "config"
    return "unknown"


def _classify_validation_profile(observed_commands: Iterable[str] | None) -> str:
    text = "\n".join(str(command) for command in (observed_commands or [])).lower()
    markers: set[str] = set()
    if re.search(r"\b(pytest|vitest|node --test|pnpm test|npm test|yarn test)\b", text):
        markers.add("tests")
    if re.search(r"\b(typecheck|vue-tsc|tsc\b|mypy|pyright)\b", text):
        markers.add("typecheck")
    if re.search(r"\b(build|turbo build|nuxt build|vite build)\b", text):
        markers.add("build")
    if re.search(r"\b(browser_|browser qa|playwright|screenshot|visual)\b", text):
        markers.add("browser_qa")
    return "+".join(marker for marker in _VALIDATION_ORDER if marker in markers) or "none"


def _iso_from_epoch(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat()
