"""Readable LLM summaries for web-chat read-aloud."""

from __future__ import annotations

import logging
import re
import time
from typing import Callable

from fastapi import HTTPException, status

READ_ALOUD_SUMMARY_MAX_INPUT_CHARS = 60_000
READ_ALOUD_SUMMARY_MAX_CHARS = 6_000

HiddenAgent = Callable[..., str]
logger = logging.getLogger(__name__)


def generate_read_aloud_summary(
    text: str,
    *,
    hidden_agent: HiddenAgent,
    model: str | None = None,
    provider: str | None = None,
    reasoning_effort: str | None = None,
) -> str:
    """Rewrite a message into a natural spoken summary."""
    source = text.strip()
    if not source:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No text to summarize")

    fast_summary = _plain_short_message_summary(source)
    if fast_summary:
        return fast_summary

    prompt = _build_read_aloud_summary_prompt(source)

    started = time.perf_counter()
    try:
        result = _generate_summary_with_auxiliary_llm(prompt, model=model, provider=provider)
        source_name = "auxiliary_llm"
    except ImportError:
        try:
            result = hidden_agent(
                prompt,
                conversation_history=[],
                model=model,
                provider=provider,
                reasoning_effort=reasoning_effort,
            )
            source_name = "hidden_agent"
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to generate read-aloud summary") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Direct read-aloud summary generation failed; falling back to hidden agent: %s", exc)
        try:
            result = hidden_agent(
                prompt,
                conversation_history=[],
                model=model,
                provider=provider,
                reasoning_effort=reasoning_effort,
            )
            source_name = "hidden_agent_fallback"
        except HTTPException:
            raise
        except Exception as fallback_exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to generate read-aloud summary") from fallback_exc
    summary = _clean_spoken_summary(result)
    if not summary and source_name == "auxiliary_llm":
        logger.warning("Direct read-aloud summary generation returned no text; falling back to hidden agent")
        try:
            result = hidden_agent(
                prompt,
                conversation_history=[],
                model=model,
                provider=provider,
                reasoning_effort=reasoning_effort,
            )
            source_name = "hidden_agent_empty_fallback"
            summary = _clean_spoken_summary(result)
        except HTTPException:
            raise
        except Exception as fallback_exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to generate read-aloud summary") from fallback_exc

    logger.info(
        "Generated read-aloud summary via %s in %.2fs from %s chars",
        source_name,
        time.perf_counter() - started,
        len(source),
    )

    if not summary:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Read-aloud summary returned no text")
    return summary


_TECHNICAL_MARKERS = re.compile(
    r"```|`[^`]+`|^\s*[-*+]\s+|^\s*\d+\.\s+|\{\s*\"|\bTraceback\b|\bError:\b|\bException\b|\n\s*[+\-] |[/~][\w./-]{12,}|\b\w+\.\w{1,8}\b",
    re.MULTILINE,
)


def _plain_short_message_summary(source: str) -> str:
    """Return only tiny, already-spoken-friendly messages without LLM latency."""
    if len(source) > 1_000 or _TECHNICAL_MARKERS.search(source):
        return ""

    sentences = re.findall(r"[^.!?…]+[.!?…]+|[^.!?…]+$", source)
    if len([sentence for sentence in sentences if sentence.strip()]) > 1:
        return ""

    return _clean_spoken_summary(source)


def _build_read_aloud_summary_prompt(source: str) -> str:
    return (
        "Fast task: turn the assistant message below into a human, listenable spoken retelling.\n"
        "Do not browse, inspect files, run tools, execute commands, read history, or gather extra context.\n"
        "Use only the text provided in this prompt and answer immediately.\n"
        "Use the same language as the message.\n"
        "Do not narrate the message line by line and do not preserve the original structure.\n"
        "Retell it like a helpful person speaking naturally: what matters, what changed, what was verified, what failed, and what remains next.\n"
        "Keep all important meaning, warnings, failures, verification results, and next steps, but compress repetitive or low-value detail.\n"
        "Do not read raw code, CSS classes, long file paths, exact filenames lists, stack traces, JSON, diffs, or command output in detail.\n"
        "Mention technical artifacts only when important, and describe them generally.\n"
        "Do not say that this is a summary or retelling.\n"
        "Do not include secrets, credentials, tokens, or API keys.\n"
        "Return only the spoken text.\n\n"
        "Assistant message:\n"
        f"{source[:READ_ALOUD_SUMMARY_MAX_INPUT_CHARS]}"
    )


def _generate_summary_with_auxiliary_llm(prompt: str, *, model: str | None, provider: str | None) -> str:
    from agent.auxiliary_client import call_llm

    response = call_llm(
        task="title_generation",
        provider=provider,
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2_000,
        temperature=0.2,
        timeout=90,
    )
    return str(response.choices[0].message.content or "")


def _clean_spoken_summary(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "")).strip().strip('"')
    if len(text) <= READ_ALOUD_SUMMARY_MAX_CHARS:
        return text
    return text[: READ_ALOUD_SUMMARY_MAX_CHARS - 1].rstrip() + "…"
