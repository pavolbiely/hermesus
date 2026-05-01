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
_PROGRESS_KEYWORDS = ("slice", "slices", "batch", "batches", "file", "files", "remaining", "left")


@dataclass(frozen=True)
class WebChatEtaClassification:
    task_type: str = "unknown"
    project_area: str = "unknown"
    validation_profile: str = "none"


@dataclass(frozen=True)
class EtaWorkUnits:
    source: str
    total: float
    completed: float
    remaining: float
    confidence: str
    labels: tuple[str, ...] = ()


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
                eta_source TEXT NOT NULL DEFAULT 'task_plan',
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
        _ensure_column(conn, "web_chat_eta_samples", "eta_source", "TEXT NOT NULL DEFAULT 'task_plan'")
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_web_chat_eta_samples_lookup
            ON web_chat_eta_samples(
                profile, workspace, provider, model, max_turns,
                task_type, project_area, validation_profile, eta_source, created_at DESC
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


def work_units_from_task_plan(task_plan: dict[str, Any] | None, *, require_remaining: bool = True) -> EtaWorkUnits | None:
    total = total_task_count(task_plan)
    if total <= 0:
        return None
    remaining = remaining_task_weight(task_plan)
    if require_remaining and remaining <= 0:
        return None
    labels = tuple(str(item.get("content") or "") for item in task_items(task_plan) if item.get("content"))
    return EtaWorkUnits(
        source="task_plan",
        total=float(total),
        completed=float(completed_task_count(task_plan)),
        remaining=remaining,
        confidence="high",
        labels=labels,
    )


def looks_like_progress_text(text: str | None) -> bool:
    if not isinstance(text, str) or not text:
        return False
    lowered = text.lower()
    return any(keyword in lowered for keyword in _PROGRESS_KEYWORDS)


def work_units_from_progress_text(texts: Iterable[str] | None) -> EtaWorkUnits | None:
    text = "\n".join(str(item) for item in (texts or []) if item).lower()
    if not text:
        return None

    patterns = [
        r"\b(?:slice|slices)\s+(\d+)\s*/\s*(\d+)\b",
        r"\b(?:slice|slices)\s+(\d+)\s+of\s+(\d+)\b",
        r"\b(?:batch|batches)\s+(\d+)\s*/\s*(\d+)\b",
        r"\b(?:batch|batches)\s+(\d+)\s+of\s+(\d+)\b",
        r"\b(?:file|files)\s+(\d+)\s*/\s*(\d+)\b",
        r"\b(\d+)\s+of\s+(\d+)\s+(?:files|slices|batches)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        current = max(0, int(match.group(1)))
        total = max(1, int(match.group(2)))
        completed = min(current, total)
        remaining = max(0.5, float(total - completed))
        return EtaWorkUnits(
            source="explicit_progress",
            total=float(total),
            completed=float(completed),
            remaining=remaining,
            confidence="medium",
        )

    remaining_match = re.search(r"\b(\d+)\s+(?:files|slices|batches)\s+(?:left|remaining)\b", text)
    if remaining_match:
        remaining = max(1, int(remaining_match.group(1)))
        return EtaWorkUnits(
            source="explicit_progress",
            total=float(remaining),
            completed=0.0,
            remaining=float(remaining),
            confidence="low",
        )
    return None


def work_units_from_runtime_fallback(
    context: Any,
    *,
    started_at: float,
    now: float,
    observed_commands: Iterable[str] | None = None,
    tool_event_count: int = 0,
) -> EtaWorkUnits | None:
    elapsed_ms = max(0, round((now - started_at) * 1000))
    classification = classify_task(context, None, observed_commands=observed_commands)
    task_type = classification.task_type

    if elapsed_ms < 20_000 and tool_event_count <= 0:
        remaining = 1.5 if task_type in {"refactor", "feature"} else 1.0
        return EtaWorkUnits("prompt_fallback", remaining, 0.0, remaining, "low")

    remaining = 2.0 if task_type in {"refactor", "feature"} else 1.0
    if task_type in {"research", "bugfix"}:
        remaining = 1.5
    if tool_event_count >= 8:
        remaining += 0.5
    if elapsed_ms >= 10 * 60 * 1000:
        remaining = max(0.5, remaining - 0.5)
    return EtaWorkUnits("runtime_fallback", remaining, 0.0, remaining, "low")


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
    progress_texts: Iterable[str] | None = None,
    tool_event_count: int = 0,
) -> None:
    units = (
        work_units_from_task_plan(latest_task_plan, require_remaining=False)
        or work_units_from_progress_text(progress_texts)
        or work_units_from_runtime_fallback(
            context,
            started_at=time.time() - (max(0, int(duration_ms)) / 1000),
            now=time.time(),
            observed_commands=observed_commands,
            tool_event_count=tool_event_count,
        )
    )
    if units is None:
        return

    ensure_eta_schema(db)
    classification = classify_task(context, latest_task_plan, workspace_changes, observed_commands)
    active_duration_ms = max(0, int(duration_ms) - max(0, int(prompt_wait_duration_ms)))
    task_count = max(1, round(units.total))
    completed_count = max(0, min(task_count, round(units.completed)))
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
        units.source,
        task_count,
        completed_count,
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
                task_type, project_area, validation_profile, eta_source,
                task_count, completed_task_count, duration_ms, active_duration_ms,
                tool_duration_ms, prompt_wait_duration_ms, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        conn.execute(
            """
            DELETE FROM web_chat_eta_samples
            WHERE id IN (
                SELECT id FROM web_chat_eta_samples
                WHERE profile IS ? AND workspace IS ? AND provider IS ? AND model IS ? AND max_turns IS ?
                  AND task_type = ? AND project_area = ? AND validation_profile = ? AND eta_source = ? AND status = 'completed'
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
                units.source,
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
    progress_texts: Iterable[str] | None = None,
    tool_event_count: int = 0,
) -> WebChatRunEta | None:
    now = now or time.time()
    units = (
        work_units_from_task_plan(task_plan)
        or work_units_from_progress_text(progress_texts)
        or work_units_from_runtime_fallback(
            context,
            started_at=started_at,
            now=now,
            observed_commands=observed_commands,
            tool_event_count=tool_event_count,
        )
    )
    if units is None or units.remaining <= 0:
        return None

    ensure_eta_schema(db)
    classification = classify_task(context, task_plan, observed_commands=observed_commands)
    lookup = _calibrated_slice_ms(db, context, classification, eta_source=units.source)
    slice_ms = lookup[0] if lookup else DEFAULT_SLICE_MS
    basis = lookup[1] if lookup else "default"
    sample_count = lookup[2] if lookup else 0

    elapsed_ms = max(0, round((now - started_at) * 1000))
    completed = int(units.completed)
    if completed > 0 and elapsed_ms >= 60_000:
        observed_slice_ms = max(1, round(elapsed_ms / completed))
        slice_ms = round((0.65 * slice_ms) + (0.35 * observed_slice_ms))
        basis = "observed" if basis == "default" else basis

    remaining_ms = max(1, round(units.remaining * slice_ms))
    confidence = _eta_confidence(units, basis, sample_count)
    updated_at = _iso_from_epoch(now)
    return WebChatRunEta(
        remainingMs=remaining_ms,
        estimatedCompletionAt=_iso_from_epoch(now + (remaining_ms / 1000)),
        confidence=confidence,  # type: ignore[arg-type]
        basis=basis,  # type: ignore[arg-type]
        taskType=classification.task_type,
        projectArea=classification.project_area,
        validationProfile=classification.validation_profile,
        totalSlices=max(1, round(units.total)),
        completedSlices=max(0, min(max(1, round(units.total)), round(units.completed))),
        sliceMs=slice_ms,
        updatedAt=updated_at,
        source=units.source,
        isApproximate=units.source != "task_plan" or confidence == "low",
    )


def _calibrated_slice_ms(
    db: SessionDB,
    context: Any,
    classification: WebChatEtaClassification,
    *,
    eta_source: str = "task_plan",
) -> tuple[int, str, int] | None:
    profile = getattr(context, "profile", None)
    workspace = getattr(context, "workspace", None)
    provider = getattr(context, "provider", None)
    model = getattr(context, "model", None)
    max_turns = getattr(context, "max_turns", None)
    source_filter = "AND eta_source = ?" if eta_source == "task_plan" else "AND eta_source != 'task_plan'"
    queries = [
        (
            f"""
            SELECT active_duration_ms, task_count FROM web_chat_eta_samples
            WHERE status = 'completed' AND profile IS ? AND workspace IS ? AND provider IS ? AND model IS ? AND max_turns IS ?
              AND task_type = ? AND project_area = ? AND validation_profile = ? {source_filter}
            ORDER BY created_at DESC LIMIT 20
            """,
            (profile, workspace, provider, model, max_turns, classification.task_type, classification.project_area, classification.validation_profile),
            "validation_profile",
        ),
        (
            f"""
            SELECT active_duration_ms, task_count FROM web_chat_eta_samples
            WHERE status = 'completed' AND profile IS ? AND workspace IS ? AND provider IS ? AND model IS ? AND max_turns IS ?
              AND task_type = ? AND project_area = ? {source_filter}
            ORDER BY created_at DESC LIMIT 20
            """,
            (profile, workspace, provider, model, max_turns, classification.task_type, classification.project_area),
            "project_area",
        ),
        (
            f"""
            SELECT active_duration_ms, task_count FROM web_chat_eta_samples
            WHERE status = 'completed' AND profile IS ? AND workspace IS ? AND provider IS ? AND model IS ? AND max_turns IS ?
              AND task_type = ? {source_filter}
            ORDER BY created_at DESC LIMIT 20
            """,
            (profile, workspace, provider, model, max_turns, classification.task_type),
            "task_type",
        ),
        (
            f"""
            SELECT active_duration_ms, task_count FROM web_chat_eta_samples
            WHERE status = 'completed' AND profile IS ? AND workspace IS ? AND provider IS ? AND model IS ? AND max_turns IS ? {source_filter}
            ORDER BY created_at DESC LIMIT 20
            """,
            (profile, workspace, provider, model, max_turns),
            "workspace_model",
        ),
        (
            f"""
            SELECT active_duration_ms, task_count FROM web_chat_eta_samples
            WHERE status = 'completed' AND profile IS ? AND workspace IS ? AND max_turns IS ? {source_filter}
            ORDER BY created_at DESC LIMIT 20
            """,
            (profile, workspace, max_turns),
            "workspace",
        ),
        (
            f"""
            SELECT active_duration_ms, task_count FROM web_chat_eta_samples
            WHERE status = 'completed' AND profile IS ? AND max_turns IS ? {source_filter}
            ORDER BY created_at DESC LIMIT 20
            """,
            (profile, max_turns),
            "profile",
        ),
    ]

    with db._lock:
        for sql, params, basis in queries:
            full_params = (*params, eta_source) if eta_source == "task_plan" else params
            rows = db._conn.execute(sql, full_params).fetchall()
            slice_values = [max(1, row["active_duration_ms"] // max(1, row["task_count"])) for row in rows]
            if slice_values:
                return round(statistics.median(slice_values)), basis, len(slice_values)
    return None


def _eta_confidence(units: EtaWorkUnits, basis: str, sample_count: int) -> str:
    if units.source not in {"task_plan", "explicit_progress"}:
        return "low"
    if sample_count >= 5 and basis in {"validation_profile", "project_area", "task_type"}:
        return "high" if units.source == "task_plan" else "medium"
    if sample_count >= 3 or units.confidence == "medium":
        return "medium"
    return "low"


def _ensure_column(conn: Any, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


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
    if any(part in {"tests", "test", "__tests__"} for part in parts) or normalized.name.endswith((".test.ts", ".test.mjs", "_test.py")):
        return "tests"
    if parts[:2] == ("web", "app") or parts[:2] == ("apps", "platform") or normalized.suffix in {".vue", ".css"}:
        return "frontend"
    if (parts and parts[0] == "backend") or normalized.suffix == ".py":
        return "backend"
    if (parts and parts[0] in {"database", "migrations"}) or normalized.suffix == ".sql":
        return "database"
    if (parts and parts[0] == "docs") or normalized.name.lower() in {"readme.md", "agents.md"}:
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
