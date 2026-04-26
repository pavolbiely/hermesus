"""Git status and persisted workspace-change helpers for web chat."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
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


def workspace_root(workspace: str | None = None) -> Path | None:
    candidate = Path(workspace or os.getcwd()).expanduser()
    try:
        root = subprocess.run(
            ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except Exception:
        return None
    return Path(root) if root else None


def git_status_porcelain(workspace: str | None, *, workspace_root_func: Callable[[str | None], Path | None] = workspace_root) -> str | None:
    root = workspace_root_func(workspace)
    if not root:
        return None
    try:
        return subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except Exception:
        return None


def status_paths(status_text: str) -> set[str]:
    paths: set[str] = set()
    for line in status_text.splitlines():
        if not line:
            continue
        value = line[3:] if len(line) > 3 else line
        if " -> " in value:
            value = value.rsplit(" -> ", 1)[-1]
        if value:
            paths.add(value)
    return paths


def workspace_changes_since(
    workspace: str,
    baseline_status: str,
    run_id: str | None,
    *,
    workspace_root_func: Callable[[str | None], Path | None] = workspace_root,
    workspace_changes_func: Callable[[str | None], WebChatWorkspaceChanges],
    workspace_patch_func: Callable[[Path, list[WebChatFileChange]], tuple[dict[str, Any] | None, bool]],
) -> WebChatWorkspaceChanges:
    root = workspace_root_func(workspace)
    if not root:
        return WebChatWorkspaceChanges(files=[], totalFiles=0, totalAdditions=0, totalDeletions=0)

    baseline_paths = status_paths(baseline_status)
    current = workspace_changes_func(str(root))
    files = sorted(
        [file for file in current.files if file.path not in baseline_paths],
        key=lambda file: file.path,
    )
    patch, patch_truncated = workspace_patch_func(root, files)
    return WebChatWorkspaceChanges(
        files=files,
        totalFiles=len(files),
        totalAdditions=sum(file.additions for file in files),
        totalDeletions=sum(file.deletions for file in files),
        workspace=str(root),
        runId=run_id,
        patch=patch,
        patchTruncated=patch_truncated,
    )


def workspace_patch(
    root: Path,
    files: list[WebChatFileChange],
    *,
    max_patch_bytes_per_file: int,
    max_patch_bytes_per_run: int,
) -> tuple[dict[str, Any] | None, bool]:
    patch_files: list[dict[str, Any]] = []
    total_bytes = 0
    truncated_any = False

    for file in files:
        patch_text = file_patch(root, file)
        truncated = False
        if patch_text is not None:
            encoded = patch_text.encode("utf-8", errors="ignore")
            if len(encoded) > max_patch_bytes_per_file:
                patch_text = encoded[:max_patch_bytes_per_file].decode("utf-8", errors="ignore")
                truncated = True
            total_bytes += len(patch_text.encode("utf-8", errors="ignore"))
            if total_bytes > max_patch_bytes_per_run:
                patch_text = None
                truncated = True
        truncated_any = truncated_any or truncated
        patch_files.append({
            "path": file.path,
            "status": file.status,
            "patch": patch_text,
            "truncated": truncated,
        })

    return ({"files": patch_files} if patch_files else None), truncated_any


def file_patch(root: Path, file: WebChatFileChange) -> str | None:
    if file.status == "created" and not is_git_tracked(root, file.path):
        return untracked_file_patch(root, file.path)

    try:
        result = subprocess.run(
            ["git", "-C", str(root), "diff", "--", file.path],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None
    return result.stdout or None


def is_git_tracked(root: Path, path: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(root), "ls-files", "--error-unmatch", path],
        capture_output=True,
        text=True,
        timeout=10,
    ).returncode == 0


def untracked_file_patch(root: Path, path: str) -> str | None:
    file_path = root / path
    try:
        data = file_path.read_bytes()
    except Exception:
        return None
    if b"\0" in data:
        return None
    text = data.decode("utf-8", errors="ignore")
    lines = text.splitlines()
    header = [
        "diff --git a/{path} b/{path}".format(path=path),
        "new file mode 100644",
        "--- /dev/null",
        f"+++ b/{path}",
        f"@@ -0,0 +1,{len(lines)} @@",
    ]
    body = [f"+{line}" for line in lines]
    return "\n".join(header + body) + "\n"


def workspace_changes(
    workspace: str | None = None,
    *,
    workspace_root_func: Callable[[str | None], Path | None] = workspace_root,
) -> WebChatWorkspaceChanges:
    root = workspace_root_func(workspace)
    if not root:
        return WebChatWorkspaceChanges(files=[], totalFiles=0, totalAdditions=0, totalDeletions=0)

    try:
        numstat_result = subprocess.run(
            ["git", "-C", str(root), "diff", "--numstat", "HEAD", "--"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        status_result = subprocess.run(
            ["git", "-C", str(root), "diff", "--name-status", "HEAD", "--"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return WebChatWorkspaceChanges(files=[], totalFiles=0, totalAdditions=0, totalDeletions=0)

    statuses = git_name_statuses(status_result.stdout)
    files: list[WebChatFileChange] = []
    seen_paths: set[str] = set()
    for line in numstat_result.stdout.splitlines():
        additions, deletions, path = line.split("\t", 2)
        if additions == "-" or deletions == "-":
            add_count = 0
            delete_count = 0
        else:
            add_count = int(additions)
            delete_count = int(deletions)
        files.append(WebChatFileChange(path=path, status=statuses.get(path, "edited"), additions=add_count, deletions=delete_count))
        seen_paths.add(path)

    for path in git_untracked_files(root):
        if path in seen_paths:
            continue
        files.append(WebChatFileChange(path=path, status="created", additions=count_text_lines(root / path), deletions=0))

    return WebChatWorkspaceChanges(
        files=files,
        totalFiles=len(files),
        totalAdditions=sum(file.additions for file in files),
        totalDeletions=sum(file.deletions for file in files),
    )


def git_name_statuses(output: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    labels = {
        "A": "created",
        "M": "edited",
        "D": "deleted",
        "R": "renamed",
        "C": "copied",
    }
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        code = parts[0][:1]
        path = parts[-1]
        statuses[path] = labels.get(code, "edited")
    return statuses


def git_untracked_files(root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return []
    return [line for line in result.stdout.splitlines() if line]


def count_text_lines(path: Path) -> int:
    try:
        data = path.read_bytes()
    except Exception:
        return 0
    if b"\0" in data:
        return 0
    text = data.decode("utf-8", errors="ignore")
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)
