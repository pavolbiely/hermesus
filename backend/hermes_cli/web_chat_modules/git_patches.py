"""Git patch formatting helpers for web chat workspace changes."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .models import WebChatFileChange


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


