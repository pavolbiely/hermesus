"""Safe local file previews for web chat."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Callable

from fastapi import HTTPException, status

from .git_changes import workspace_root
from .models import WebChatFilePreview

MAX_FILE_PREVIEW_BYTES = 256 * 1024
TEXT_MIME_PREFIXES = ("text/",)
TEXT_EXTENSIONS = {
    ".bash",
    ".c",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".dart",
    ".env",
    ".go",
    ".graphql",
    ".h",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".log",
    ".lua",
    ".md",
    ".mjs",
    ".php",
    ".plist",
    ".py",
    ".rb",
    ".rs",
    ".scss",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
    ".zsh",
}
LANGUAGE_BY_EXTENSION = {
    ".bash": "bash",
    ".c": "c",
    ".conf": "ini",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".css": "css",
    ".csv": "csv",
    ".dart": "dart",
    ".env": "dotenv",
    ".go": "go",
    ".graphql": "graphql",
    ".h": "c",
    ".html": "html",
    ".ini": "ini",
    ".java": "java",
    ".js": "javascript",
    ".json": "json",
    ".jsx": "jsx",
    ".kt": "kotlin",
    ".lua": "lua",
    ".md": "markdown",
    ".mjs": "javascript",
    ".php": "php",
    ".plist": "xml",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".scss": "scss",
    ".sh": "bash",
    ".sql": "sql",
    ".swift": "swift",
    ".toml": "toml",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".txt": "text",
    ".vue": "vue",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".zsh": "bash",
}
LANGUAGE_BY_FILENAME = {
    ".env": "dotenv",
    ".env.example": "dotenv",
    ".gitignore": "gitignore",
    "Dockerfile": "dockerfile",
    "Makefile": "makefile",
    "README": "markdown",
}
MEDIA_TYPE_BY_EXTENSION = {
    ".md": "text/markdown",
    ".ts": "text/typescript",
    ".tsx": "text/tsx",
    ".vue": "text/vue",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
}

WorkspaceValidator = Callable[[str | None], Path | None]


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def preview_file(requested_path: str, workspace: str | None, *, validate_workspace: WorkspaceValidator) -> WebChatFilePreview:
    value = requested_path.strip()
    if not value:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Path is required")

    workspace_root_path = validate_workspace(workspace)
    if workspace_root_path is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select a workspace before previewing relative files",
        )

    workspace_root_path = workspace_root_path.resolve()
    git_root_path = (workspace_root(str(workspace_root_path)) or workspace_root_path).resolve()
    allowed_roots = _unique_roots([workspace_root_path, git_root_path])
    path = _resolve_preview_path(value, workspace_root_path, git_root_path, allowed_roots)

    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    media_type = _media_type(path)
    size = path.stat().st_size
    language = _language(path)
    relative_path = _relative_path(path, git_root_path) or _relative_path(path, workspace_root_path)

    if not _is_text_previewable(path, media_type):
        return WebChatFilePreview(
            path=str(path),
            requestedPath=requested_path,
            relativePath=relative_path,
            name=path.name,
            mediaType=media_type,
            size=size,
            language=language,
            content=None,
            previewable=False,
            reason="File type cannot be previewed as text",
        )

    raw = path.read_bytes()[: MAX_FILE_PREVIEW_BYTES + 1]
    truncated = len(raw) > MAX_FILE_PREVIEW_BYTES
    raw = raw[:MAX_FILE_PREVIEW_BYTES]
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("utf-8", errors="replace")

    return WebChatFilePreview(
        path=str(path),
        requestedPath=requested_path,
        relativePath=relative_path,
        name=path.name,
        mediaType=media_type,
        size=size,
        language=language,
        content=content,
        truncated=truncated,
        previewable=True,
    )


def _resolve_preview_path(value: str, workspace_root_path: Path, git_root_path: Path, allowed_roots: list[Path]) -> Path:
    candidate = Path(value).expanduser()
    candidates = [candidate.resolve()] if candidate.is_absolute() else [
        (workspace_root_path / candidate).resolve(),
        (git_root_path / candidate).resolve(),
    ]

    escaped_candidate: Path | None = None
    for path in _unique_paths(candidates):
        if not any(is_within(path, root) for root in allowed_roots):
            escaped_candidate = path
            continue
        if path.exists():
            return path

    if escaped_candidate is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is outside the selected workspace")
    return candidates[0]


def _unique_roots(paths: list[Path]) -> list[Path]:
    roots: list[Path] = []
    for path in paths:
        if path not in roots:
            roots.append(path)
    return roots


def _unique_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def _relative_path(path: Path, root: Path) -> str | None:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return None


def _media_type(path: Path) -> str:
    if path.suffix in MEDIA_TYPE_BY_EXTENSION:
        return MEDIA_TYPE_BY_EXTENSION[path.suffix]
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _language(path: Path) -> str | None:
    return LANGUAGE_BY_FILENAME.get(path.name) or LANGUAGE_BY_EXTENSION.get(path.suffix)


def _is_text_previewable(path: Path, media_type: str) -> bool:
    return path.suffix in TEXT_EXTENSIONS or media_type.startswith(TEXT_MIME_PREFIXES) or _looks_like_utf8_text(path)


def _looks_like_utf8_text(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:4096]
    except OSError:
        return False
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True
