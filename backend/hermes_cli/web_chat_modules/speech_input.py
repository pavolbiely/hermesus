"""Speech-to-text helpers for web-chat voice input."""

from __future__ import annotations

import os
from io import BytesIO
from typing import Any

from fastapi import HTTPException, UploadFile, status

_DEFAULT_ELEVENLABS_STT_MODEL_ID = "scribe_v2"
_DEFAULT_OPENAI_STT_MODEL_ID = "gpt-4o-transcribe"


async def transcribe_speech_input_response(
    file: UploadFile,
    *,
    provider: str | None = None,
    api_key: str | None = None,
    language: str | None = None,
) -> str:
    normalized_provider = _normalize_speech_input_provider(provider)
    if normalized_provider == "elevenlabs":
        return await _transcribe_elevenlabs(file, api_key=api_key, language=language)
    if normalized_provider == "openai":
        return await _transcribe_openai(file, api_key=api_key, language=language)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported speech input provider: {normalized_provider}.",
    )


def _normalize_speech_input_provider(provider: str | None) -> str:
    value = provider.strip().lower() if provider else ""
    if value in {"elevenlabs", "eleven-labs"}:
        return "elevenlabs"
    if value in {"openai", "openai-transcribe", "gpt-4o-transcribe"}:
        return "openai"
    return value or "browser"


async def _transcribe_elevenlabs(file: UploadFile, *, api_key: str | None, language: str | None) -> str:
    try:
        import tools.tts_tool as tts_tool
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hermes speech input provider is not available in this runtime.",
        ) from exc

    try:
        ElevenLabs = getattr(tts_tool, "_import_elevenlabs")()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ElevenLabs speech input is not available in this runtime.",
        ) from exc

    resolved_api_key = _resolve_elevenlabs_api_key(tts_tool, api_key)
    audio = await file.read()
    if not audio:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Audio file is empty.")

    client = ElevenLabs(api_key=resolved_api_key)
    options = _elevenlabs_stt_options(tts_tool, language)
    response = client.speech_to_text.convert(
        file=(file.filename or "voice-input.webm", audio, file.content_type or "audio/webm"),
        **options,
    )
    text = _response_text(response)
    if not text:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="ElevenLabs returned an empty transcript.")
    return text


async def _transcribe_openai(file: UploadFile, *, api_key: str | None, language: str | None) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenAI speech input is not available in this runtime.",
        ) from exc

    resolved_api_key = _resolve_openai_api_key(api_key)
    audio = await file.read()
    if not audio:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Audio file is empty.")

    audio_file = BytesIO(audio)
    audio_file.name = file.filename or "voice-input.webm"
    client = OpenAI(api_key=resolved_api_key)
    try:
        response = client.audio.transcriptions.create(
            file=audio_file,
            **_openai_stt_options(language),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_openai_transcription_error_detail(exc),
        ) from exc
    text = _response_text(response)
    if not text:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="OpenAI returned an empty transcript.")
    return text


def _resolve_elevenlabs_api_key(tts_tool: Any, api_key: str | None) -> str:
    normalized_api_key = api_key.strip() if api_key else None
    if normalized_api_key:
        return normalized_api_key

    get_env_value = getattr(tts_tool, "get_env_value", None)
    env_api_key = get_env_value("ELEVENLABS_API_KEY") if callable(get_env_value) else os.environ.get("ELEVENLABS_API_KEY")
    if env_api_key:
        return str(env_api_key)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="ElevenLabs API key is required for ElevenLabs speech input.",
    )


def _resolve_openai_api_key(api_key: str | None) -> str:
    normalized_api_key = api_key.strip() if api_key else None
    if normalized_api_key:
        return normalized_api_key

    env_api_key = _runtime_env_value("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if env_api_key:
        return str(env_api_key)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="OpenAI API key is required for OpenAI speech input.",
    )


def _runtime_env_value(name: str) -> str | None:
    try:
        import tools.tts_tool as tts_tool
    except ImportError:
        return None

    get_env_value = getattr(tts_tool, "get_env_value", None)
    if not callable(get_env_value):
        return None
    value = get_env_value(name)
    return str(value) if value else None


def _elevenlabs_stt_options(tts_tool: Any, language: str | None) -> dict[str, Any]:
    config = _load_tts_config(tts_tool)
    provider_config = config.get("elevenlabs") if isinstance(config.get("elevenlabs"), dict) else {}
    options: dict[str, Any] = {
        "model_id": str(provider_config.get("stt_model_id") or _DEFAULT_ELEVENLABS_STT_MODEL_ID),
    }
    language_code = _normalize_language_code(language)
    if language_code:
        options["language_code"] = language_code
    return options


def _openai_stt_options(language: str | None) -> dict[str, Any]:
    options: dict[str, Any] = {"model": _DEFAULT_OPENAI_STT_MODEL_ID}
    language_code = _normalize_language_code(language)
    if language_code:
        options["language"] = language_code
    return options


def _openai_transcription_error_detail(exc: Exception) -> str:
    status_code = getattr(exc, "status_code", None)
    if status_code in {401, 403}:
        return "OpenAI rejected the speech-input request. Check the OpenAI API key."
    if status_code == 429:
        return "OpenAI speech input is rate-limited or out of quota."
    if isinstance(status_code, int) and 400 <= status_code < 500:
        return f"OpenAI rejected the speech-input audio request with HTTP {status_code}."
    return "OpenAI speech input failed while transcribing audio."


def _load_tts_config(tts_tool: Any) -> dict[str, Any]:
    loader = getattr(tts_tool, "_load_tts_config", None)
    if not callable(loader):
        return {}
    config = loader()
    return config if isinstance(config, dict) else {}


def _normalize_language_code(language: str | None) -> str | None:
    value = language.strip().lower() if language else ""
    if not value:
        return None
    return value.split("-")[0]


def _response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text.strip()
    if isinstance(response, dict):
        value = response.get("text")
        if isinstance(value, str):
            return value.strip()
    model_dump = getattr(response, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict) and isinstance(dumped.get("text"), str):
            return dumped["text"].strip()
    return ""
