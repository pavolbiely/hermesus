"""Tests for web-chat runtime ETA calibration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EtaContext:
    input: str = "Implement UI polish"
    profile: str | None = "hermesum"
    workspace: str | None = "/repo"
    provider: str | None = "openai"
    model: str | None = "gpt-5.5"
    reasoning_effort: str | None = "high"
    max_turns: int | None = 90


def task_plan(*statuses: str) -> dict:
    return {
        "items": [
            {"id": str(index), "content": f"Task {index}", "status": status}
            for index, status in enumerate(statuses, start=1)
        ]
    }


def rows(db):
    with db._lock:
        return db._conn.execute("SELECT * FROM web_chat_eta_samples ORDER BY id").fetchall()


def eta_db(tmp_path):
    from hermes_state import SessionDB

    return SessionDB(tmp_path / "eta.sqlite")


def test_eta_schema_and_sample_insert_subtracts_prompt_wait(_isolate_hermes_home, tmp_path):
    from hermes_cli.web_chat_modules.run_eta import ensure_eta_schema, record_eta_sample

    db = eta_db(tmp_path)
    ensure_eta_schema(db)

    record_eta_sample(
        db,
        EtaContext(input="Fix backend bug"),
        task_plan("completed", "completed"),
        duration_ms=1_200_000,
        tool_duration_ms=100_000,
        prompt_wait_duration_ms=300_000,
        status="completed",
        workspace_changes={"files": [{"path": "backend/hermes_cli/web_chat.py"}]},
    )

    sample = rows(db)[0]
    assert sample["task_count"] == 2
    assert sample["completed_task_count"] == 2
    assert sample["duration_ms"] == 1_200_000
    assert sample["active_duration_ms"] == 900_000
    assert sample["task_type"] == "bugfix"
    assert sample["project_area"] == "backend"


def test_empty_task_plan_records_prompt_fallback_sample(_isolate_hermes_home, tmp_path):
    from hermes_cli.web_chat_modules.run_eta import ensure_eta_schema, record_eta_sample

    db = eta_db(tmp_path)
    ensure_eta_schema(db)
    record_eta_sample(db, EtaContext(input="ok"), {"items": []}, duration_ms=1000, progress_texts=[])

    sample = rows(db)[0]
    assert sample["eta_source"] == "prompt_fallback"
    assert sample["task_count"] == 1


def test_classification_project_area_and_validation_profile():
    from hermes_cli.web_chat_modules.run_eta import classify_task

    plan = task_plan("pending")
    frontend = classify_task(
        EtaContext(input="Polish UI"),
        plan,
        workspace_changes={"files": [{"path": "web/app/components/Foo.vue"}]},
        observed_commands=["pnpm typecheck", "browser_vision screenshot", "pnpm test"],
    )
    backend = classify_task(
        EtaContext(input="Fix API"),
        plan,
        workspace_changes={"files": [{"path": "backend/hermes_cli/web_chat.py"}]},
    )
    mixed = classify_task(
        EtaContext(input="Implement feature"),
        plan,
        workspace_changes={"files": [{"path": "backend/api.py"}, {"path": "web/app/pages/index.vue"}]},
    )

    assert frontend.task_type == "ui"
    assert frontend.project_area == "frontend"
    assert frontend.validation_profile == "tests+typecheck+browser_qa"
    assert backend.project_area == "backend"
    assert mixed.project_area == "multi_area"


def test_estimate_eta_from_explicit_slice_progress_without_task_plan(_isolate_hermes_home, tmp_path):
    from hermes_cli.web_chat_modules.run_eta import estimate_run_eta

    eta = estimate_run_eta(
        eta_db(tmp_path),
        EtaContext(input="Continue the refactor"),
        None,
        started_at=0,
        now=10,
        progress_texts=["Working through slice 2/6"],
    )

    assert eta is not None
    assert eta.source == "explicit_progress"
    assert eta.isApproximate is True
    assert eta.totalSlices == 6
    assert eta.completedSlices == 2
    assert eta.remainingMs == 40 * 60 * 1000
    assert eta.confidence == "medium"


def test_estimate_eta_from_batch_progress_without_task_plan(_isolate_hermes_home, tmp_path):
    from hermes_cli.web_chat_modules.run_eta import estimate_run_eta

    eta = estimate_run_eta(
        eta_db(tmp_path),
        EtaContext(input="Refactor files"),
        None,
        started_at=0,
        now=10,
        progress_texts=["Batch 3 of 10 complete"],
    )

    assert eta is not None
    assert eta.source == "explicit_progress"
    assert eta.totalSlices == 10
    assert eta.completedSlices == 3
    assert eta.remainingMs == 70 * 60 * 1000


def test_estimate_eta_prompt_fallback_without_task_plan(_isolate_hermes_home, tmp_path):
    from hermes_cli.web_chat_modules.run_eta import estimate_run_eta

    eta = estimate_run_eta(
        eta_db(tmp_path),
        EtaContext(input="Refactor web chat sidebar into smaller modules"),
        None,
        started_at=0,
        now=10,
    )

    assert eta is not None
    assert eta.source == "prompt_fallback"
    assert eta.isApproximate is True
    assert eta.confidence == "low"
    assert eta.remainingMs == 15 * 60 * 1000


def test_progress_text_parser_handles_remaining_files():
    from hermes_cli.web_chat_modules.run_eta import work_units_from_progress_text

    units = work_units_from_progress_text(["7 files remaining"])

    assert units is not None
    assert units.source == "explicit_progress"
    assert units.remaining == 7
    assert work_units_from_progress_text(["no useful progress here"]) is None


def test_default_eta_uses_ten_minutes_per_slice(_isolate_hermes_home, tmp_path):
    from hermes_cli.web_chat_modules.run_eta import estimate_run_eta

    eta = estimate_run_eta(
        eta_db(tmp_path),
        EtaContext(),
        task_plan("pending", "in_progress", "completed", "pending"),
        started_at=0,
        now=10,
    )

    assert eta is not None
    assert eta.remainingMs == 25 * 60 * 1000
    assert eta.totalSlices == 4
    assert eta.completedSlices == 1
    assert eta.confidence == "low"
    assert eta.basis == "default"


def test_historical_sample_changes_slice_baseline(_isolate_hermes_home, tmp_path):
    from hermes_cli.web_chat_modules.run_eta import estimate_run_eta, record_eta_sample

    db = eta_db(tmp_path)
    context = EtaContext(input="Polish UI")
    record_eta_sample(
        db,
        context,
        task_plan("completed", "completed"),
        duration_ms=600_000,
        workspace_changes={"files": [{"path": "web/app/components/Foo.vue"}]},
    )

    eta = estimate_run_eta(
        db,
        context,
        task_plan("pending", "pending"),
        started_at=0,
        now=10,
    )

    assert eta is not None
    assert eta.sliceMs == 300_000
    assert eta.remainingMs == 600_000
    assert eta.basis == "validation_profile"


def test_classification_specific_samples_beat_workspace_fallback(_isolate_hermes_home, tmp_path):
    from hermes_cli.web_chat_modules.run_eta import estimate_run_eta, record_eta_sample

    db = eta_db(tmp_path)
    context = EtaContext(input="Polish UI")
    record_eta_sample(
        db,
        EtaContext(input="Maintain backend"),
        task_plan("completed"),
        duration_ms=1_500_000,
        workspace_changes={"files": [{"path": "backend/api.py"}]},
    )
    record_eta_sample(
        db,
        context,
        task_plan("completed"),
        duration_ms=300_000,
        workspace_changes={"files": [{"path": "web/app/components/Foo.vue"}]},
    )

    eta = estimate_run_eta(db, context, task_plan("pending"), started_at=0, now=10)

    assert eta is not None
    assert eta.sliceMs == 300_000
    assert eta.basis == "validation_profile"


def test_validation_heavy_sample_does_not_affect_no_validation_exact_match(_isolate_hermes_home, tmp_path):
    from hermes_cli.web_chat_modules.run_eta import estimate_run_eta, record_eta_sample

    db = eta_db(tmp_path)
    context = EtaContext(input="Polish UI")
    changes = {"files": [{"path": "web/app/components/Foo.vue"}]}
    record_eta_sample(db, context, task_plan("completed"), duration_ms=1_200_000, workspace_changes=changes, observed_commands=["pnpm typecheck"])
    record_eta_sample(db, context, task_plan("completed"), duration_ms=300_000, workspace_changes=changes, observed_commands=[])

    eta = estimate_run_eta(db, context, task_plan("pending"), started_at=0, now=10, observed_commands=[])

    assert eta is not None
    assert eta.sliceMs == 300_000
    assert eta.validationProfile == "none"
