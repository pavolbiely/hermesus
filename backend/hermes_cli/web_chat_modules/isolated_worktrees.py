"""Profile-local isolated Git worktree helpers for web chat."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fastapi import HTTPException, status
from hermes_state import SessionDB

from .models import WebChatIsolatedWorkspace
from .workspace_settings import user_home

_SAFE_SESSION_RE = re.compile(r"[^A-Za-z0-9_-]+")


@dataclass(frozen=True)
class CleanupResult:
    session_id: str
    worktree_path: str
    status: str
    removed: bool


def ensure_isolated_worktree_schema(db: SessionDB) -> None:
    def _do(conn):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS web_chat_isolated_worktrees (
                session_id TEXT NOT NULL,
                source_workspace TEXT NOT NULL,
                source_git_root TEXT NOT NULL,
                worktree_path TEXT NOT NULL,
                branch_name TEXT NOT NULL,
                base_ref TEXT NOT NULL,
                profile TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (session_id, source_git_root)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_web_chat_isolated_worktrees_session ON web_chat_isolated_worktrees(session_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_web_chat_isolated_worktrees_source ON web_chat_isolated_worktrees(source_git_root)"
        )

    db._execute_write(_do)


def source_workspace_hash(source_git_root: str) -> str:
    return hashlib.sha256(str(Path(source_git_root).resolve()).encode("utf-8")).hexdigest()[:16]


def safe_session_slug(session_id: str) -> str:
    slug = _SAFE_SESSION_RE.sub("-", session_id).strip("-")
    if slug:
        return slug[:80]
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]


def isolated_worktree_base_dir(profile: str | None) -> Path:
    override = os.environ.get("HERMES_WEB_CHAT_WORKTREE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    profile_name = safe_session_slug(profile or "default")
    return user_home() / ".hermes" / "profiles" / profile_name / "web-chat" / "worktrees"


def isolated_worktree_path(*, profile: str | None, source_git_root: str, session_id: str) -> Path:
    return isolated_worktree_base_dir(profile) / source_workspace_hash(source_git_root) / safe_session_slug(session_id)


def isolated_branch_name(*, source_git_root: str, session_id: str) -> str:
    return f"web-chat/{source_workspace_hash(source_git_root)}/{safe_session_slug(session_id)}"


def record_isolated_worktree(
    db: SessionDB,
    *,
    session_id: str,
    source_workspace: str,
    source_git_root: str,
    worktree_path: str,
    branch_name: str,
    base_ref: str,
    profile: str | None,
    status_value: str = "active",
) -> None:
    ensure_isolated_worktree_schema(db)
    now = time.time()

    def _do(conn):
        conn.execute(
            """
            INSERT INTO web_chat_isolated_worktrees (
                session_id, source_workspace, source_git_root, worktree_path,
                branch_name, base_ref, profile, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, source_git_root) DO UPDATE SET
                source_workspace = excluded.source_workspace,
                worktree_path = excluded.worktree_path,
                branch_name = excluded.branch_name,
                base_ref = excluded.base_ref,
                profile = excluded.profile,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                session_id,
                source_workspace,
                source_git_root,
                worktree_path,
                branch_name,
                base_ref,
                profile,
                status_value,
                now,
                now,
            ),
        )

    db._execute_write(_do)


def isolated_worktree_for_session(
    db: SessionDB,
    session_id: str,
    source_git_root: str | None = None,
) -> WebChatIsolatedWorkspace | None:
    ensure_isolated_worktree_schema(db)
    with db._lock:
        if source_git_root:
            row = db._conn.execute(
                """
                SELECT * FROM web_chat_isolated_worktrees
                WHERE session_id = ? AND source_git_root = ?
                """,
                (session_id, source_git_root),
            ).fetchone()
        else:
            row = db._conn.execute(
                """
                SELECT * FROM web_chat_isolated_worktrees
                WHERE session_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
    if not row:
        return None
    return _row_to_model(row)


def update_isolated_worktree_status(
    db: SessionDB,
    *,
    session_id: str,
    source_git_root: str,
    status_value: str,
) -> None:
    ensure_isolated_worktree_schema(db)

    def _do(conn):
        conn.execute(
            """
            UPDATE web_chat_isolated_worktrees
            SET status = ?, updated_at = ?
            WHERE session_id = ? AND source_git_root = ?
            """,
            (status_value, time.time(), session_id, source_git_root),
        )

    db._execute_write(_do)


def ensure_session_worktree(
    db: SessionDB,
    *,
    session_id: str,
    source_workspace: str | None,
    profile: str | None,
    workspace_root_func: Callable[[str | None], Path | None],
) -> WebChatIsolatedWorkspace | None:
    if not source_workspace:
        return None

    source_root = workspace_root_func(source_workspace)
    if not source_root:
        return None

    source_git_root = str(source_root.resolve())
    if not _has_head(source_git_root):
        return None

    existing = isolated_worktree_for_session(db, session_id, source_git_root)
    if existing and _is_valid_git_worktree(Path(existing.worktreePath)):
        existing.dirty = is_worktree_dirty(existing.worktreePath)
        return existing
    if existing and Path(existing.worktreePath).exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Isolated workspace path exists but is not a valid Git worktree.",
        )

    worktree_path = isolated_worktree_path(profile=profile, source_git_root=source_git_root, session_id=session_id)
    branch_name = isolated_branch_name(source_git_root=source_git_root, session_id=session_id)
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    if worktree_path.exists() and not _is_valid_git_worktree(worktree_path):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Isolated workspace path already exists and is not a Git worktree.",
        )

    if not worktree_path.exists():
        _add_worktree(source_git_root, worktree_path, branch_name)

    record_isolated_worktree(
        db,
        session_id=session_id,
        source_workspace=str(Path(source_workspace).resolve()),
        source_git_root=source_git_root,
        worktree_path=str(worktree_path),
        branch_name=branch_name,
        base_ref="HEAD",
        profile=profile,
    )
    return WebChatIsolatedWorkspace(
        sessionId=session_id,
        sourceWorkspace=str(Path(source_workspace).resolve()),
        sourceGitRoot=source_git_root,
        worktreePath=str(worktree_path),
        branchName=branch_name,
        baseRef="HEAD",
        status="active",
        dirty=is_worktree_dirty(str(worktree_path)),
    )


def remove_session_worktree(db: SessionDB, session_id: str, *, status_value: str = "deleted") -> None:
    worktree = isolated_worktree_for_session(db, session_id)
    if not worktree:
        return
    path = Path(worktree.worktreePath)
    if path.exists():
        _remove_worktree(worktree.sourceGitRoot, path, force=True)
    else:
        _prune_worktrees(worktree.sourceGitRoot)
    update_isolated_worktree_status(
        db,
        session_id=session_id,
        source_git_root=worktree.sourceGitRoot,
        status_value=status_value,
    )


def cleanup_old_isolated_worktrees(
    db: SessionDB,
    *,
    older_than_days: int = 30,
    active_session_ids: set[str] | None = None,
) -> list[CleanupResult]:
    ensure_isolated_worktree_schema(db)
    cutoff = time.time() - older_than_days * 24 * 60 * 60
    active_session_ids = active_session_ids or set()
    with db._lock:
        rows = db._conn.execute(
            "SELECT * FROM web_chat_isolated_worktrees WHERE updated_at < ?",
            (cutoff,),
        ).fetchall()

    results: list[CleanupResult] = []
    for row in rows:
        model = _row_to_model(row)
        if model.sessionId in active_session_ids:
            continue
        path = Path(model.worktreePath)
        if path.exists() and is_worktree_dirty(model.worktreePath) and model.status not in {"applied", "cleaned", "missing"}:
            continue
        if path.exists():
            _remove_worktree(model.sourceGitRoot, path)
        else:
            _prune_worktrees(model.sourceGitRoot)
        update_isolated_worktree_status(
            db,
            session_id=model.sessionId,
            source_git_root=model.sourceGitRoot,
            status_value="cleaned",
        )
        results.append(CleanupResult(model.sessionId, model.worktreePath, "cleaned", True))
    return results


def is_worktree_dirty(worktree_path: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", worktree_path, "status", "--porcelain=v1"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return False
    return bool(result.stdout.strip())


def _row_to_model(row) -> WebChatIsolatedWorkspace:
    return WebChatIsolatedWorkspace(
        sessionId=row["session_id"],
        sourceWorkspace=row["source_workspace"],
        sourceGitRoot=row["source_git_root"],
        worktreePath=row["worktree_path"],
        branchName=row["branch_name"],
        baseRef=row["base_ref"],
        status=row["status"],
        dirty=is_worktree_dirty(row["worktree_path"]) if Path(row["worktree_path"]).exists() else False,
    )


def _is_valid_git_worktree(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return False
    return True


def _has_head(source_git_root: str) -> bool:
    try:
        subprocess.run(
            ["git", "-C", source_git_root, "rev-parse", "--verify", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return False
    return True


def _add_worktree(source_git_root: str, worktree_path: Path, branch_name: str) -> None:
    first = subprocess.run(
        ["git", "-C", source_git_root, "worktree", "add", "-b", branch_name, str(worktree_path), "HEAD"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if first.returncode == 0:
        return
    second = subprocess.run(
        ["git", "-C", source_git_root, "worktree", "add", str(worktree_path), branch_name],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if second.returncode != 0:
        detail = second.stderr.strip() or first.stderr.strip() or "Could not create isolated Git worktree."
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


def _remove_worktree(source_git_root: str, worktree_path: Path, *, force: bool = False) -> None:
    command = ["git", "-C", source_git_root, "worktree", "remove"]
    if force:
        command.append("--force")
    command.append(str(worktree_path))
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "Could not remove isolated Git worktree."
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _prune_worktrees(source_git_root: str) -> None:
    subprocess.run(
        ["git", "-C", source_git_root, "worktree", "prune"],
        capture_output=True,
        text=True,
        timeout=30,
    )
