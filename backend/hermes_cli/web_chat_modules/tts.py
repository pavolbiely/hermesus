"""Text-to-speech helpers for web-chat response read-aloud."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse

_MEDIA_TYPES = {
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
}

_TTS_CONFIG_OVERRIDE_LOCK = threading.Lock()
_TTS_CACHE_LOCK = threading.Lock()
_TTS_CACHE_KEY_LOCKS: dict[str, threading.Lock] = {}
_TTS_CACHE_SCHEMA_VERSION = 1
_TTS_CACHE_MAX_FILES = 200
_VOICE_ID_PROVIDERS = {"elevenlabs", "minimax", "mistral", "xai"}
_VOICE_NAME_PROVIDERS = {"edge", "openai", "gemini", "kittentts", "piper"}
_EDGE_VOICE_BY_LANGUAGE = {
    "cs": "cs-CZ-AntoninNeural",
    "de": "de-DE-ConradNeural",
    "en": "en-US-BrianNeural",
    "es": "es-ES-AlvaroNeural",
    "fr": "fr-FR-HenriNeural",
    "it": "it-IT-DiegoNeural",
    "pl": "pl-PL-MarekNeural",
    "pt": "pt-PT-DuarteNeural",
    "sk": "sk-SK-LukasNeural",
    "uk": "uk-UA-OstapNeural",
}
_LANGUAGE_PATTERNS = (
    ("sk", r"[áäčďéíľĺňóôŕšťúýž]|\b(ako|alebo|preto|ktor[ýáé]|môže|môžem|odpoveď|správ[aei]|tento|táto|bolo|bude|nie je|áno)\b"),
    ("cs", r"[ěůř]|\b(jako|nebo|proto|kter[ýáé]|může|odpověď|správn[ěá]|tento|bylo|bude|není|ano)\b"),
    ("pl", r"[ąćęłńóśźż]|\b(jak|albo|ponieważ|który|może|odpowiedź|będzie|nie jest|tak)\b"),
    ("de", r"[äöüß]|\b(und|oder|nicht|dass|kann|antwort|werden|ist|eine|der|die|das)\b"),
    ("fr", r"[àâçéèêëîïôùûüÿœ]|\b(et|ou|pas|que|peut|réponse|sera|est|une|les|des)\b"),
    ("es", r"[¿¡áéíóúñü]|\b(y|o|no|que|puede|respuesta|será|está|una|los|las)\b"),
    ("pt", r"[ãõáâçéêíóôú]|\b(e|ou|não|que|pode|resposta|será|está|uma|os|as)\b"),
    ("it", r"\b(e|o|non|che|può|risposta|sarà|è|una|gli|dei)\b"),
    ("uk", r"[іїєґ]"),
)


def synthesize_speech_response(text: str, voice: str | None = None, speed: float | None = None) -> FileResponse:
    """Generate TTS audio with Hermes' configured provider and return it inline."""
    try:
        import tools.tts_tool as tts_tool
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hermes TTS provider is not available in this runtime.",
        ) from exc

    normalized_voice = voice.strip() if voice else None
    cache_key = _tts_cache_key(tts_tool, text=text, voice=normalized_voice, speed=speed)
    key_lock = _tts_cache_key_lock(cache_key)

    with key_lock:
        cached_path = _cached_tts_file(cache_key)
        if cached_path:
            return _audio_file_response(cached_path, cache_status="hit")

        if normalized_voice:
            result = _synthesize_with_voice_override(tts_tool, text, normalized_voice, speed)
        else:
            result = _synthesize_with_edge_language_voice(tts_tool, text, speed)
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(result.get("error") or "TTS generation failed."),
            )

        file_path = Path(str(result.get("file_path") or "")).expanduser()
        if not file_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="TTS generation did not produce an audio file.",
            )

        cached_path = _store_tts_cache_file(cache_key, file_path)
        return _audio_file_response(cached_path, cache_status="miss")


def stream_speech_response(text: str, speed: float | None = None) -> FileResponse | StreamingResponse:
    """Stream Edge TTS audio directly while filling the server-side cache."""
    try:
        import edge_tts
        import tools.tts_tool as tts_tool
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Edge TTS streaming is not available in this runtime.",
        ) from exc

    cache_key = _tts_cache_key(tts_tool, text=text, voice=None, speed=speed)
    cached_path = _cached_tts_file(cache_key)
    if cached_path:
        return _audio_file_response(cached_path, cache_status="hit")

    voice = _EDGE_VOICE_BY_LANGUAGE.get(_detect_language_code(text)) or _EDGE_VOICE_BY_LANGUAGE["en"]
    return StreamingResponse(
        _stream_edge_tts_to_cache(edge_tts, text=text, voice=voice, speed=speed, cache_key=cache_key),
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "X-Hermes-TTS-Cache": "miss"},
    )


async def _stream_edge_tts_to_cache(
    edge_tts: Any,
    *,
    text: str,
    voice: str,
    speed: float | None,
    cache_key: str,
) -> AsyncIterator[bytes]:
    cache_dir = _tts_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{cache_key}.mp3"
    temp_path = cache_dir / f"{cache_key}.{threading.get_ident()}.tmp"
    completed = False

    try:
        communicate = edge_tts.Communicate(text, voice=voice, rate=_edge_rate(speed))
        with temp_path.open("wb") as output:
            async for chunk in communicate.stream():
                if chunk.get("type") != "audio":
                    continue
                data = chunk.get("data")
                if not data:
                    continue
                output.write(data)
                yield data
        completed = True
    finally:
        if completed and temp_path.exists():
            temp_path.replace(cache_path)
            cache_path.touch(exist_ok=True)
            _prune_tts_cache(cache_dir)
        elif temp_path.exists():
            temp_path.unlink()


def _audio_file_response(file_path: Path, *, cache_status: str | None = None) -> FileResponse:
    headers = {"X-Hermes-TTS-Cache": cache_status} if cache_status else None
    return FileResponse(
        file_path,
        media_type=_MEDIA_TYPES.get(file_path.suffix.lower(), "application/octet-stream"),
        filename=file_path.name,
        content_disposition_type="inline",
        headers=headers,
    )


def _tts_cache_key(tts_tool: Any, *, text: str, voice: str | None, speed: float | None) -> str:
    base_config = _load_tts_config(tts_tool)
    effective_config = (
        _tts_config_with_voice_override(tts_tool, base_config, voice, speed)
        if voice
        else _tts_config_with_edge_language_voice(base_config, text, speed)
    )
    payload = {
        "version": _TTS_CACHE_SCHEMA_VERSION,
        "text": text,
        "speed": speed,
        "voice": voice,
        "effective_config": effective_config,
    }
    serialized = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _load_tts_config(tts_tool: Any) -> dict[str, Any]:
    config = tts_tool._load_tts_config()
    return dict(config) if isinstance(config, dict) else {}


def _tts_cache_key_lock(cache_key: str) -> threading.Lock:
    with _TTS_CACHE_LOCK:
        lock = _TTS_CACHE_KEY_LOCKS.get(cache_key)
        if lock is None:
            lock = threading.Lock()
            _TTS_CACHE_KEY_LOCKS[cache_key] = lock
        return lock


def _tts_cache_dir() -> Path:
    try:
        from hermes_constants import get_hermes_home

        root = get_hermes_home()
    except Exception:
        root = Path.home() / ".hermes"
    return root / "web-chat" / "tts-cache"


def _cached_tts_file(cache_key: str) -> Path | None:
    cache_dir = _tts_cache_dir()
    for path in cache_dir.glob(f"{cache_key}.*"):
        if path.is_file() and path.suffix != ".tmp":
            path.touch(exist_ok=True)
            return path
    return None


def _store_tts_cache_file(cache_key: str, source_path: Path) -> Path:
    suffix = source_path.suffix.lower() or ".mp3"
    cache_dir = _tts_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{cache_key}{suffix}"
    if not cache_path.exists():
        shutil.copyfile(source_path, cache_path)
    cache_path.touch(exist_ok=True)
    _prune_tts_cache(cache_dir)
    return cache_path


def _prune_tts_cache(cache_dir: Path) -> None:
    files = sorted(
        (path for path in cache_dir.iterdir() if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in files[_TTS_CACHE_MAX_FILES:]:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _synthesize_with_voice_override(tts_tool: Any, text: str, voice: str, speed: float | None) -> dict[str, Any]:
    """Call Hermes TTS with a request-local voice override.

    Hermes' TTS tool intentionally reads voice/provider from config.yaml and
    does not accept a voice argument. For web settings we keep the override
    browser-local and temporarily patch the config loader for this request.
    """
    original_loader = tts_tool._load_tts_config

    def load_config_with_voice() -> dict[str, Any]:
        return _tts_config_with_voice_override(tts_tool, original_loader(), voice, speed)

    with _TTS_CONFIG_OVERRIDE_LOCK:
        tts_tool._load_tts_config = load_config_with_voice
        try:
            return _parse_tool_result(tts_tool.text_to_speech_tool(text=text))
        finally:
            tts_tool._load_tts_config = original_loader


def _tts_config_with_voice_override(tts_tool: Any, config: Any, voice: str, speed: float | None) -> dict[str, Any]:
    next_config = dict(config) if isinstance(config, dict) else {}
    provider = _tts_provider(tts_tool, next_config)

    if not provider:
        return next_config

    if speed is not None:
        next_config["speed"] = speed

    if provider in _VOICE_ID_PROVIDERS:
        _set_provider_option(next_config, provider, "voice_id", voice)
    elif provider in _VOICE_NAME_PROVIDERS:
        _set_provider_option(next_config, provider, "voice", voice)
    elif provider == "neutts":
        _set_provider_option(next_config, provider, "ref_audio", voice)
    else:
        providers = next_config.get("providers") if isinstance(next_config.get("providers"), dict) else {}
        provider_config = dict(providers.get(provider)) if isinstance(providers.get(provider), dict) else {}
        provider_config["voice"] = voice
        next_config["providers"] = {**providers, provider: provider_config}

    return next_config


def _tts_provider(tts_tool: Any, config: dict[str, Any]) -> str:
    get_provider = getattr(tts_tool, "_get_provider", None)
    if callable(get_provider):
        return str(get_provider(config)).strip().lower()
    return str(config.get("provider") or "edge").strip().lower()


def _set_provider_option(config: dict[str, Any], provider: str, key: str, value: Any) -> None:
    provider_config = config.get(provider) if isinstance(config.get(provider), dict) else {}
    config[provider] = {**provider_config, key: value}


def _synthesize_with_edge_language_voice(tts_tool: Any, text: str, speed: float | None) -> dict[str, Any]:
    original_loader = tts_tool._load_tts_config

    def load_config_with_detected_voice() -> dict[str, Any]:
        return _tts_config_with_edge_language_voice(original_loader(), text, speed)

    with _TTS_CONFIG_OVERRIDE_LOCK:
        tts_tool._load_tts_config = load_config_with_detected_voice
        try:
            return _parse_tool_result(tts_tool.text_to_speech_tool(text=text))
        finally:
            tts_tool._load_tts_config = original_loader


def _tts_config_with_edge_language_voice(config: Any, text: str, speed: float | None) -> dict[str, Any]:
    next_config = dict(config) if isinstance(config, dict) else {}
    next_config["provider"] = "edge"

    voice = _EDGE_VOICE_BY_LANGUAGE.get(_detect_language_code(text))
    if voice:
        _set_provider_option(next_config, "edge", "voice", voice)
    if speed is not None:
        _set_provider_option(next_config, "edge", "speed", speed)
    return next_config


def _detect_language_code(text: str) -> str:
    sample = text[:2000]
    for language, pattern in _LANGUAGE_PATTERNS:
        if re.search(pattern, sample, re.IGNORECASE):
            return language
    return "en"


def _edge_rate(speed: float | None) -> str:
    if speed is None or speed == 1:
        return "+0%"
    percentage = round((speed - 1) * 100)
    return f"{percentage:+d}%"


def _parse_tool_result(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="TTS provider returned an invalid response.",
        ) from exc

    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="TTS provider returned an invalid response.",
        )
    return parsed
