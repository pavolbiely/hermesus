"""Git status and workspace diff helpers for web chat."""

from __future__ import annotations

import os
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from .models import WebChatFileChange, WebChatWorkspaceChanges
from .git_patches import (
    file_patch,
    is_git_tracked,
    untracked_file_patch,
    workspace_patch,
)
from .persisted_git_changes import (
    copy_session_git_changes,
    delete_session_git_changes,
    delete_session_git_changes_after_message,
    ensure_git_change_schema,
    record_session_git_changes,
    session_git_changes_by_message,
)


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


def workspace_change_fingerprint(
    workspace: str | None,
    *,
    workspace_root_func: Callable[[str | None], Path | None] = workspace_root,
) -> str | None:
    root = workspace_root_func(workspace)
    if not root:
        return None

    try:
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
        diff = subprocess.run(
            ["git", "-C", str(root), "diff", "--binary", "HEAD", "--"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except Exception:
        return None

    digest = sha256()
    digest.update(status.encode("utf-8", errors="surrogateescape"))
    digest.update(b"\0")
    digest.update(diff.encode("utf-8", errors="surrogateescape"))
    for path in git_untracked_files(root):
        digest.update(b"\0untracked\0")
        digest.update(path.encode("utf-8", errors="surrogateescape"))
        try:
            digest.update((root / path).read_bytes())
        except Exception:
            continue
    return digest.hexdigest()


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
