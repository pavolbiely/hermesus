"""Readable LLM summaries for web-chat read-aloud."""

from __future__ import annotations

import re
from typing import Callable

from fastapi import HTTPException, status

READ_ALOUD_SUMMARY_MAX_INPUT_CHARS = 60_000
READ_ALOUD_SUMMARY_MAX_CHARS = 6_000

HiddenAgent = Callable[..., str]


def generate_read_aloud_summary(text: str, *, hidden_agent: HiddenAgent) -> str:
    """Rewrite a message into a natural spoken summary."""
    source = text.strip()
    if not source:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No text to summarize")

    prompt = (
        "Rewrite the assistant message below as a natural, human-friendly spoken read-aloud version.\n"
        "Use the same language as the message.\n"
        "Do not be overly brief, but keep it comfortable to listen to.\n"
        "Explain what was done, decided, or found in clear prose.\n"
        "Do not read raw code, CSS classes, long file paths, exact filenames lists, stack traces, JSON, diffs, or command output in detail.\n"
        "Mention technical artifacts only when they are important, and describe them generally.\n"
        "Preserve important warnings, failures, verification results, and next steps.\n"
        "Do not say that this is a summary.\n"
        "Do not include secrets, credentials, tokens, or API keys.\n"
        "Return only the spoken text.\n\n"
        "Assistant message:\n"
        f"{source[:READ_ALOUD_SUMMARY_MAX_INPUT_CHARS]}"
    )

    try:
        result = hidden_agent(prompt, conversation_history=[])
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to generate read-aloud summary") from exc

    summary = _clean_spoken_summary(result)
    if not summary:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Read-aloud summary returned no text")
    return summary


def _clean_spoken_summary(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "")).strip().strip('"')
    if len(text) <= READ_ALOUD_SUMMARY_MAX_CHARS:
        return text
    return text[: READ_ALOUD_SUMMARY_MAX_CHARS - 1].rstrip() + "…"
