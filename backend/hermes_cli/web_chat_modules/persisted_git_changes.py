"""Persisted workspace-change storage helpers for web chat."""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from hermes_state import SessionDB

from .models import WebChatFileChange, WebChatWorkspaceChanges


def ensure_git_change_schema(db: SessionDB) -> None:
    def _do(conn):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS web_chat_git_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                run_id TEXT,
                message_id INTEGER,
                workspace TEXT NOT NULL,
                baseline_status TEXT,
                final_status TEXT NOT NULL,
                files_json TEXT NOT NULL,
                patch_json TEXT,
                patch_truncated INTEGER NOT NULL DEFAULT 0,
                total_files INTEGER NOT NULL DEFAULT 0,
                total_additions INTEGER NOT NULL DEFAULT 0,
                total_deletions INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_web_chat_git_changes_session ON web_chat_git_changes(session_id, created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_web_chat_git_changes_message ON web_chat_git_changes(message_id)"
        )

    db._execute_write(_do)


def record_session_git_changes(
    db: SessionDB,
    *,
    session_id: str,
    run_id: str | None,
    message_id: int | None,
    workspace: str,
    baseline_status: str | None,
    final_status: str,
    changes: WebChatWorkspaceChanges,
) -> None:
    if not changes.files:
        return

    ensure_git_change_schema(db)
    files_json = json.dumps([file.model_dump() for file in changes.files], separators=(",", ":"))
    patch_json = json.dumps(changes.patch, separators=(",", ":")) if changes.patch else None

    def _do(conn):
        conn.execute(
            """
            INSERT INTO web_chat_git_changes (
                session_id, run_id, message_id, workspace, baseline_status, final_status,
                files_json, patch_json, patch_truncated, total_files, total_additions,
                total_deletions, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                run_id,
                message_id,
                workspace,
                baseline_status,
                final_status,
                files_json,
                patch_json,
                1 if changes.patchTruncated else 0,
                changes.totalFiles,
                changes.totalAdditions,
                changes.totalDeletions,
                time.time(),
            ),
        )

    db._execute_write(_do)


def session_git_changes_by_message(
    db: SessionDB,
    session_id: str,
    *,
    iso_from_epoch: Callable[[Any], str],
) -> dict[str, WebChatWorkspaceChanges]:
    ensure_git_change_schema(db)
    with db._lock:
        rows = db._conn.execute(
            """
            SELECT * FROM web_chat_git_changes
            WHERE session_id = ? AND message_id IS NOT NULL
            ORDER BY created_at ASC, id ASC
            """,
            (session_id,),
        ).fetchall()

    changes_by_message: dict[str, WebChatWorkspaceChanges] = {}
    for row in rows:
        try:
            files = [WebChatFileChange(**item) for item in json.loads(row["files_json"] or "[]")]
            patch = json.loads(row["patch_json"]) if row["patch_json"] else None
        except Exception:
            continue
        changes_by_message[str(row["message_id"])] = WebChatWorkspaceChanges(
            files=files,
            totalFiles=row["total_files"],
            totalAdditions=row["total_additions"],
            totalDeletions=row["total_deletions"],
            workspace=row["workspace"],
            runId=row["run_id"],
            capturedAt=iso_from_epoch(row["created_at"]),
            patch=patch,
            patchTruncated=bool(row["patch_truncated"]),
        )
    return changes_by_message


def copy_session_git_changes(
    db: SessionDB,
    *,
    source_session_id: str,
    target_session_id: str,
    message_id_map: dict[int, int],
    record_changes: Callable[..., None] = record_session_git_changes,
) -> None:
    ensure_git_change_schema(db)
    with db._lock:
        rows = db._conn.execute(
            "SELECT * FROM web_chat_git_changes WHERE session_id = ? ORDER BY created_at ASC, id ASC",
            (source_session_id,),
        ).fetchall()

    for row in rows:
        source_message_id = row["message_id"]
        target_message_id = message_id_map.get(source_message_id) if source_message_id is not None else None
        files = [WebChatFileChange(**item) for item in json.loads(row["files_json"] or "[]")]
        record_changes(
            db,
            session_id=target_session_id,
            run_id=row["run_id"],
            message_id=target_message_id,
            workspace=row["workspace"],
            baseline_status=row["baseline_status"],
            final_status=row["final_status"],
            changes=WebChatWorkspaceChanges(
                files=files,
                totalFiles=row["total_files"],
                totalAdditions=row["total_additions"],
                totalDeletions=row["total_deletions"],
                workspace=row["workspace"],
                runId=row["run_id"],
                patch=json.loads(row["patch_json"]) if row["patch_json"] else None,
                patchTruncated=bool(row["patch_truncated"]),
            ),
        )


def delete_session_git_changes(db: SessionDB, session_id: str) -> None:
    ensure_git_change_schema(db)

    def _do(conn):
        conn.execute("DELETE FROM web_chat_git_changes WHERE session_id = ?", (session_id,))

    db._execute_write(_do)


def delete_session_git_changes_after_message(db: SessionDB, session_id: str, message_id: int) -> None:
    ensure_git_change_schema(db)

    def _do(conn):
        conn.execute(
            "DELETE FROM web_chat_git_changes WHERE session_id = ? AND message_id > ?",
            (session_id, message_id),
        )

    db._execute_write(_do)


