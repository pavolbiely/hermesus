"""Hermes checkout and disposable runtime update helpers."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, status

from .models import WebChatUpdateStatusResponse

RUNTIME_SOURCE_MARKER = ".hermesum-runtime-source"


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
    output = _run_git(root, ["ls-remote", "origin", f"refs/heads/{branch}"], timeout=60).stdout
    if not output:
        return None
    return output.split()[0]


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
    update_available = bool(remote_head and remote_head != upstream_head)

    return WebChatUpdateStatusResponse(
        updateAvailable=update_available,
        runtimeOutOfSync=runtime_out_of_sync,
        upstreamPath=str(upstream),
        runtimePath=str(runtime),
        branch=branch,
        currentRevision=_short(upstream_head),
        remoteRevision=_short(remote_head),
        runtimeRevision=_short(runtime_source_head),
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
