"""Hermes checkout and disposable runtime update helpers."""

from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException, status

from .models import (
    WebChatAppUpdateStatusResponse,
    WebChatUpdateCommit,
    WebChatUpdateStatusResponse,
)

RUNTIME_SOURCE_MARKER = ".hermesum-runtime-source"
APP_RESTART_EXIT_CODE = 42


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str


def project_root(start: Path | None = None) -> Path:
    configured = os.environ.get("HERMES_WEB_CHAT_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()

    current = (start or Path(__file__)).resolve()
    for parent in [current, *current.parents]:
        if (parent / "run-local.sh").is_file():
            return parent
        if parent.name == ".runtime":
            candidate = parent.parent
            if (candidate / "run-local.sh").is_file():
                return candidate
    raise RuntimeError("Could not locate Hermesum project root")


def upstream_root() -> Path:
    configured = os.environ.get("HERMES_AGENT_SOURCE")
    return Path(configured).expanduser().resolve() if configured else (Path.home() / ".hermes" / "hermes-agent")


def runtime_root(root: Path | None = None) -> Path:
    return (root or project_root()) / ".runtime" / "hermes-agent"


def _run_git(root: Path, args: list[str], *, timeout: int = 30) -> CommandResult:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "git command failed").strip())
    return CommandResult(stdout=completed.stdout.strip(), stderr=completed.stderr.strip())


def _short(value: str | None) -> str | None:
    return value[:8] if value else None


def _git_head(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    return _run_git(root, ["rev-parse", "HEAD"]).stdout or None


def _git_branch(root: Path) -> str:
    branch = _run_git(root, ["branch", "--show-current"]).stdout
    return branch or "main"


def _remote_head(root: Path, branch: str) -> str | None:
    ref = f"refs/remotes/origin/{branch}"
    _run_git(root, ["fetch", "--quiet", "origin", f"refs/heads/{branch}:{ref}"], timeout=60)
    output = _run_git(root, ["rev-parse", ref]).stdout
    return output or None


def _remote_url(root: Path) -> str | None:
    try:
        output = _run_git(root, ["remote", "get-url", "origin"]).stdout
    except Exception:
        return None
    return output or None


def _has_remote_update(root: Path, current_head: str | None, remote_head: str | None) -> bool:
    if not current_head or not remote_head or current_head == remote_head:
        return False

    result = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", current_head, remote_head],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise RuntimeError((result.stderr or result.stdout or "git merge-base failed").strip())


def _github_repo_url(remote_url: str | None) -> str | None:
    if not remote_url:
        return None

    if remote_url.startswith("git@github.com:"):
        repo = remote_url.removeprefix("git@github.com:")
    else:
        parsed = urlparse(remote_url)
        if parsed.netloc != "github.com":
            return None
        repo = parsed.path.lstrip("/")

    repo = repo.removesuffix(".git").strip("/")
    if not repo or repo.count("/") < 1:
        return None
    return f"https://github.com/{repo}"


def _github_compare_url(remote_url: str | None, current_head: str | None, remote_head: str | None) -> str | None:
    repo_url = _github_repo_url(remote_url)
    if not repo_url or not current_head or not remote_head:
        return None
    return f"{repo_url}/compare/{current_head}...{remote_head}"


def _github_commit_url(remote_url: str | None, commit_hash: str | None) -> str | None:
    repo_url = _github_repo_url(remote_url)
    if not repo_url or not commit_hash:
        return None
    return f"{repo_url}/commit/{commit_hash}"


def _update_commits(
    root: Path,
    current_head: str | None,
    remote_head: str | None,
    *,
    remote_url: str | None = None,
    limit: int = 11,
) -> list[WebChatUpdateCommit]:
    if not _has_remote_update(root, current_head, remote_head):
        return []

    output = _run_git(
        root,
        [
            "log",
            f"--max-count={limit}",
            "--format=%H%x00%h%x00%s%x00%an%x00%cI",
            f"{current_head}..{remote_head}",
        ],
    ).stdout
    commits: list[WebChatUpdateCommit] = []
    for line in output.splitlines():
        parts = line.split("\0", 4)
        if len(parts) != 5:
            continue
        full_hash, short_hash, subject, author, committed_at = parts
        commits.append(
            WebChatUpdateCommit(
                hash=full_hash,
                shortHash=short_hash,
                subject=subject,
                author=author or None,
                committedAt=committed_at or None,
                url=_github_commit_url(remote_url, full_hash),
            )
        )
    return commits


def _runtime_source_head(runtime: Path) -> str | None:
    marker = runtime / RUNTIME_SOURCE_MARKER
    if not marker.is_file():
        return None
    value = marker.read_text(encoding="utf-8").strip()
    return value or None


def update_status() -> WebChatUpdateStatusResponse:
    root = project_root()
    upstream = upstream_root()
    runtime = runtime_root(root)

    try:
        upstream_head = _git_head(upstream)
        branch = _git_branch(upstream)
        remote_head = _remote_head(upstream, branch)
        remote_url = _remote_url(upstream)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not check Hermes update status: {exc}",
        ) from exc

    if not upstream_head:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Hermes checkout is not a git repository: {upstream}",
        )

    runtime_source_head = _runtime_source_head(runtime)
    runtime_exists = (runtime / "hermes_cli" / "web_chat.py").is_file()
    runtime_out_of_sync = not runtime_exists or runtime_source_head != upstream_head
    commits = _update_commits(upstream, upstream_head, remote_head, remote_url=remote_url)
    update_available = bool(commits)
    has_more_commits = len(commits) > 10

    return WebChatUpdateStatusResponse(
        updateAvailable=update_available,
        runtimeOutOfSync=runtime_out_of_sync,
        upstreamPath=str(upstream),
        runtimePath=str(runtime),
        branch=branch,
        currentRevision=_short(upstream_head),
        remoteRevision=_short(remote_head),
        runtimeRevision=_short(runtime_source_head),
        commits=commits[:10],
        hasMoreCommits=has_more_commits,
        compareUrl=_github_compare_url(remote_url, upstream_head, remote_head),
    )


def perform_update() -> WebChatUpdateStatusResponse:
    root = project_root()
    upstream = upstream_root()

    try:
        _run_git(upstream, ["pull", "--ff-only", "--autostash"], timeout=180)
        subprocess.run(
            ["bash", str(root / "run-local.sh"), "--sync-runtime"],
            text=True,
            capture_output=True,
            timeout=180,
            check=True,
            cwd=str(root),
            env={**os.environ, "HERMES_AGENT_SOURCE": str(upstream)},
        )
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "Update command failed").strip()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return update_status()


def app_update_status() -> WebChatAppUpdateStatusResponse:
    root = project_root()

    try:
        current_head = _git_head(root)
        branch = _git_branch(root)
        remote_head = _remote_head(root, branch)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not check app update status: {exc}",
        ) from exc

    if not current_head:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"App checkout is not a git repository: {root}",
        )

    return WebChatAppUpdateStatusResponse(
        updateAvailable=_has_remote_update(root, current_head, remote_head),
        appPath=str(root),
        branch=branch,
        currentRevision=_short(current_head),
        remoteRevision=_short(remote_head),
    )


def perform_app_update() -> WebChatAppUpdateStatusResponse:
    root = project_root()

    try:
        _run_git(root, ["pull", "--ff-only", "--autostash"], timeout=180)
        _run_app_command(root, ["pnpm", "install", "--frozen-lockfile"], timeout=300)
        _run_app_command(root, ["pnpm", "build"], timeout=300)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    response = app_update_status()
    _schedule_app_restart()
    return response


def _run_app_command(root: Path, args: list[str], *, timeout: int) -> CommandResult:
    completed = subprocess.run(
        args,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        cwd=str(root / "web"),
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or f"{' '.join(args)} failed").strip()
        raise RuntimeError(message)
    return CommandResult(stdout=completed.stdout.strip(), stderr=completed.stderr.strip())


def _schedule_app_restart() -> None:
    if os.environ.get("HERMESUM_ENABLE_SELF_RESTART") != "1":
        return

    def restart() -> None:
        os._exit(APP_RESTART_EXIT_CODE)

    timer = threading.Timer(1.0, restart)
    timer.daemon = True
    timer.start()
