"""Attachment storage and lookup helpers for the web chat API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from .models import WebChatAttachment, WebChatWorkspacesResponse


WorkspaceValidator = Callable[[str | None], Path | None]
WorkspaceLister = Callable[[], WebChatWorkspacesResponse]


def attachment_root(workspace: str | None, *, validate_workspace: WorkspaceValidator) -> Path:
    root = validate_workspace(workspace)
    if not root:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select a workspace before attaching files.")
    return root / ".hermes" / "attachments"


def is_safe_attachment_id(attachment_id: str) -> bool:
    return bool(attachment_id) and attachment_id.isalnum()


def safe_filename(filename: str | None) -> str:
    name = Path(filename or "attachment").name.strip()
    cleaned = "".join(char if char.isalnum() or char in {" ", ".", "-", "_"} else "-" for char in name)
    return cleaned.strip(" .") or "attachment"


def unique_attachment_path(root: Path, filename: str) -> Path:
    candidate = root / filename
    stem = candidate.stem or "attachment"
    suffix = candidate.suffix
    index = 2
    while candidate.exists() or candidate.with_name(f"{candidate.name}.web-chat.json").exists():
        candidate = root / f"{stem} {index}{suffix}"
        index += 1
    return candidate


def attachment_meta_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.web-chat.json")


def attachment_url(attachment_id: str) -> str:
    return f"/api/web-chat/attachments/{attachment_id}/content"


def attachment_with_runtime_state(attachment: WebChatAttachment) -> WebChatAttachment:
    exists = Path(attachment.path).is_file()
    return attachment.model_copy(update={"url": attachment_url(attachment.id), "exists": exists})


def attachment_metadata_roots(
    workspace: str | None,
    *,
    known_roots: set[Path],
    validate_workspace: WorkspaceValidator,
    list_workspaces: WorkspaceLister,
) -> list[Path]:
    roots = set(known_roots)
    if workspace:
        roots.add(attachment_root(workspace, validate_workspace=validate_workspace))
    try:
        for item in list_workspaces().workspaces:
            roots.add(Path(item.path) / ".hermes" / "attachments")
    except Exception:
        pass
    return sorted(roots, key=str)


def load_attachment(
    attachment_id: str,
    workspace: str | None,
    *,
    known_roots: set[Path],
    validate_workspace: WorkspaceValidator,
    list_workspaces: WorkspaceLister,
) -> WebChatAttachment:
    if not is_safe_attachment_id(attachment_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    roots = attachment_metadata_roots(
        workspace,
        known_roots=known_roots,
        validate_workspace=validate_workspace,
        list_workspaces=list_workspaces,
    )
    for root in roots:
        if not root.is_dir():
            continue
        for meta_path in root.glob("*.web-chat.json"):
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if metadata.get("id") == attachment_id:
                return attachment_with_runtime_state(WebChatAttachment(**metadata))

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")


def resolve_attachments(
    ids: list[str] | None,
    workspace: str | None,
    *,
    known_roots: set[Path],
    validate_workspace: WorkspaceValidator,
    list_workspaces: WorkspaceLister,
) -> list[WebChatAttachment]:
    if not ids:
        return []

    attachments: list[WebChatAttachment] = []
    for attachment_id in ids:
        try:
            attachment = load_attachment(
                attachment_id,
                workspace,
                known_roots=known_roots,
                validate_workspace=validate_workspace,
                list_workspaces=list_workspaces,
            )
        except HTTPException as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment no longer exists. Upload it again.") from exc
            raise
        if not attachment.exists:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment file no longer exists. Upload it again.")
        if workspace and attachment.workspace and Path(attachment.workspace).resolve() != Path(workspace).resolve():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment belongs to a different workspace. Upload it again.")
        attachments.append(attachment)
    return attachments


def input_with_attachment_context(input_text: str, attachments: list[WebChatAttachment]) -> str:
    if not attachments:
        return input_text
    lines = ["Attached files:"]
    lines.extend(
        (
            f"- {attachment.name} (path: {attachment.path}, relative path: {attachment.relativePath}, "
            f"media type: {attachment.mediaType}, size: {attachment.size} bytes)"
        )
        for attachment in attachments
    )
    lines.append("Use file/document tools if you need to inspect them.")
    return f"{input_text}\n\n" + "\n".join(lines)


async def store_upload(
    file: UploadFile,
    workspace: str | None,
    *,
    max_attachment_bytes: int,
    known_roots: set[Path],
    validate_workspace: WorkspaceValidator,
) -> WebChatAttachment:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment is empty")
    if len(data) > max_attachment_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is too large. Maximum size is 25 MB.")

    root = attachment_root(workspace, validate_workspace=validate_workspace)
    project = root.parent.parent
    root.mkdir(parents=True, exist_ok=True)
    known_roots.add(root)

    filename = safe_filename(file.filename)
    path = unique_attachment_path(root, filename)
    path.write_bytes(data)

    attachment_id = uuid4().hex
    relative_path = path.relative_to(project)
    attachment = WebChatAttachment(
        id=attachment_id,
        name=path.name,
        mediaType=file.content_type or "application/octet-stream",
        size=len(data),
        path=str(path),
        workspace=str(project),
        relativePath=str(relative_path),
        url=attachment_url(attachment_id),
        exists=True,
    )
    attachment_meta_path(path).write_text(attachment.model_dump_json(), encoding="utf-8")
    return attachment
