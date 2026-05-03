"""Text-to-speech helpers for web-chat response read-aloud."""

from __future__ import annotations

import hashlib
import json
import os
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


class TtsProviderAdapter:
    """Small provider adapter descriptor for web-chat TTS routing."""

    def __init__(self, name: str, *, supports_streaming: bool) -> None:
        self.name = name
        self.supports_streaming = supports_streaming

    def cache_key(
        self,
        tts_tool: Any,
        *,
        text: str,
        voice: str | None,
        speed: float | None,
        api_key: str | None,
    ) -> str:
        return _tts_cache_key(
            tts_tool,
            text=text,
            voice=voice,
            speed=speed,
            provider=self.name,
            api_key=api_key,
        )


_TTS_ADAPTERS = {
    "configured": TtsProviderAdapter("configured", supports_streaming=False),
    "edge": TtsProviderAdapter("edge", supports_streaming=True),
    "elevenlabs": TtsProviderAdapter("elevenlabs", supports_streaming=True),
}


def synthesize_speech_response(
    text: str,
    voice: str | None = None,
    speed: float | None = None,
    provider: str | None = None,
    api_key: str | None = None,
) -> FileResponse:
    """Generate TTS audio with the selected adapter and return it inline."""
    try:
        import tools.tts_tool as tts_tool
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hermes TTS provider is not available in this runtime.",
        ) from exc

    normalized_voice = voice.strip() if voice else None
    adapter = _tts_adapter(provider if provider or not normalized_voice else "configured")
    normalized_api_key = api_key.strip() if api_key else None
    cache_key = adapter.cache_key(
        tts_tool,
        text=text,
        voice=normalized_voice,
        speed=speed,
        api_key=normalized_api_key,
    )
    key_lock = _tts_cache_key_lock(cache_key)

    with key_lock:
        cached_path = _cached_tts_file(cache_key)
        if cached_path:
            return _audio_file_response(cached_path, cache_status="hit")

        if adapter.name == "elevenlabs":
            cached_path = _synthesize_elevenlabs_to_cache(
                tts_tool,
                text=text,
                voice=normalized_voice,
                speed=speed,
                api_key=normalized_api_key,
                cache_key=cache_key,
            )
            return _audio_file_response(cached_path, cache_status="miss")

        if normalized_voice and adapter.name != "edge":
            result = _synthesize_with_voice_override(tts_tool, text, normalized_voice, speed)
        else:
            result = _synthesize_with_edge_language_voice(tts_tool, text, speed, voice=normalized_voice)
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


def stream_speech_response(
    text: str,
    speed: float | None = None,
    provider: str | None = None,
    voice: str | None = None,
    api_key: str | None = None,
) -> FileResponse | StreamingResponse:
    """Stream selected TTS audio directly while filling the server-side cache."""
    try:
        import tools.tts_tool as tts_tool
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hermes TTS provider is not available in this runtime.",
        ) from exc

    adapter = _tts_adapter(provider)
    normalized_voice = voice.strip() if voice else None
    normalized_api_key = api_key.strip() if api_key else None
    cache_key = adapter.cache_key(
        tts_tool,
        text=text,
        voice=normalized_voice,
        speed=speed,
        api_key=normalized_api_key,
    )
    cached_path = _cached_tts_file(cache_key)
    if cached_path:
        return _audio_file_response(cached_path, cache_status="hit")

    if adapter.name == "elevenlabs":
        return StreamingResponse(
            _stream_elevenlabs_to_cache(
                tts_tool,
                text=text,
                voice=normalized_voice,
                speed=speed,
                api_key=normalized_api_key,
                cache_key=cache_key,
            ),
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "X-Hermes-TTS-Cache": "miss"},
        )

    try:
        import edge_tts
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Edge TTS streaming is not available in this runtime.",
        ) from exc

    edge_voice = normalized_voice or _EDGE_VOICE_BY_LANGUAGE.get(_detect_language_code(text)) or _EDGE_VOICE_BY_LANGUAGE["en"]
    return StreamingResponse(
        _stream_edge_tts_to_cache(edge_tts, text=text, voice=edge_voice, speed=speed, cache_key=cache_key),
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "X-Hermes-TTS-Cache": "miss"},
    )


def _normalize_tts_provider(provider: str | None) -> str | None:
    value = provider.strip().lower() if provider else ""
    if not value or value in {"backend", "backend-tts", "hermes"}:
        return None
    if value in {"edge", "edge-tts"}:
        return "edge"
    if value in {"elevenlabs", "eleven-labs"}:
        return "elevenlabs"
    if value in {"configured", "config", "default"}:
        return "configured"
    return value


def _tts_adapter(provider: str | None) -> TtsProviderAdapter:
    normalized_provider = _normalize_tts_provider(provider) or "edge"
    adapter = _TTS_ADAPTERS.get(normalized_provider)
    if adapter is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported TTS provider: {normalized_provider}.",
        )
    return adapter


def _elevenlabs_config(tts_tool: Any, voice: str | None, speed: float | None, api_key: str | None) -> dict[str, Any]:
    config = _load_tts_config(tts_tool)
    provider_config = config.get("elevenlabs") if isinstance(config.get("elevenlabs"), dict) else {}
    get_env_value = getattr(tts_tool, "get_env_value", None)
    env_api_key = get_env_value("ELEVENLABS_API_KEY") if callable(get_env_value) else os.environ.get("ELEVENLABS_API_KEY")
    resolved_api_key = api_key or env_api_key
    if not resolved_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ElevenLabs API key is required for ElevenLabs TTS.",
        )

    return {
        "api_key": str(resolved_api_key),
        "voice_id": str(voice or provider_config.get("voice_id") or getattr(tts_tool, "DEFAULT_ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")),
        "model_id": str(provider_config.get("model_id") or getattr(tts_tool, "DEFAULT_ELEVENLABS_STREAMING_MODEL_ID", "eleven_flash_v2_5")),
        "speed": _elevenlabs_speed(speed),
    }


def _elevenlabs_audio_chunks(tts_tool: Any, *, text: str, voice: str | None, speed: float | None, api_key: str | None) -> Any:
    options = _elevenlabs_config(tts_tool, voice, speed, api_key)
    try:
        ElevenLabs = getattr(tts_tool, "_import_elevenlabs")()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ElevenLabs TTS is not available in this runtime.",
        ) from exc

    client = ElevenLabs(api_key=options["api_key"])
    convert_kwargs: dict[str, Any] = {
        "text": text,
        "voice_id": options["voice_id"],
        "model_id": options["model_id"],
        "output_format": "mp3_44100_128",
    }
    if options["speed"] is not None:
        try:
            from elevenlabs import VoiceSettings

            convert_kwargs["voice_settings"] = VoiceSettings(speed=options["speed"])
        except Exception:
            convert_kwargs["voice_settings"] = {"speed": options["speed"]}
    return client.text_to_speech.convert(**convert_kwargs)


def _synthesize_elevenlabs_to_cache(
    tts_tool: Any,
    *,
    text: str,
    voice: str | None,
    speed: float | None,
    api_key: str | None,
    cache_key: str,
) -> Path:
    cache_dir = _tts_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{cache_key}.mp3"
    temp_path = cache_dir / f"{cache_key}.{threading.get_ident()}.tmp"
    completed = False

    try:
        with temp_path.open("wb") as output:
            for chunk in _elevenlabs_audio_chunks(tts_tool, text=text, voice=voice, speed=speed, api_key=api_key):
                if chunk:
                    output.write(chunk)
        completed = True
    finally:
        if completed and temp_path.exists():
            temp_path.replace(cache_path)
            cache_path.touch(exist_ok=True)
            _prune_tts_cache(cache_dir)
        elif temp_path.exists():
            temp_path.unlink()

    return cache_path


async def _stream_elevenlabs_to_cache(
    tts_tool: Any,
    *,
    text: str,
    voice: str | None,
    speed: float | None,
    api_key: str | None,
    cache_key: str,
) -> AsyncIterator[bytes]:
    cache_dir = _tts_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{cache_key}.mp3"
    temp_path = cache_dir / f"{cache_key}.{threading.get_ident()}.tmp"
    completed = False

    try:
        with temp_path.open("wb") as output:
            for chunk in _elevenlabs_audio_chunks(tts_tool, text=text, voice=voice, speed=speed, api_key=api_key):
                if not chunk:
                    continue
                output.write(chunk)
                yield chunk
        completed = True
    finally:
        if completed and temp_path.exists():
            temp_path.replace(cache_path)
            cache_path.touch(exist_ok=True)
            _prune_tts_cache(cache_dir)
        elif temp_path.exists():
            temp_path.unlink()

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


def _tts_cache_key(
    tts_tool: Any,
    *,
    text: str,
    voice: str | None,
    speed: float | None,
    provider: str | None = None,
    api_key: str | None = None,
) -> str:
    base_config = _load_tts_config(tts_tool)
    normalized_provider = _normalize_tts_provider(provider)
    if normalized_provider == "elevenlabs":
        effective_config = _tts_config_with_elevenlabs_options(tts_tool, base_config, voice, speed)
    elif normalized_provider == "edge" or not voice:
        effective_config = _tts_config_with_edge_language_voice(base_config, text, speed, voice=voice)
    else:
        effective_config = _tts_config_with_voice_override(tts_tool, base_config, voice, speed)
    payload = {
        "version": _TTS_CACHE_SCHEMA_VERSION,
        "text": text,
        "speed": speed,
        "voice": voice,
        "provider": normalized_provider,
        "api_key_digest": hashlib.sha256(api_key.encode("utf-8")).hexdigest() if api_key else None,
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


def _synthesize_with_edge_language_voice(tts_tool: Any, text: str, speed: float | None, voice: str | None = None) -> dict[str, Any]:
    original_loader = tts_tool._load_tts_config

    def load_config_with_detected_voice() -> dict[str, Any]:
        return _tts_config_with_edge_language_voice(original_loader(), text, speed, voice=voice)

    with _TTS_CONFIG_OVERRIDE_LOCK:
        tts_tool._load_tts_config = load_config_with_detected_voice
        try:
            return _parse_tool_result(tts_tool.text_to_speech_tool(text=text))
        finally:
            tts_tool._load_tts_config = original_loader


def _tts_config_with_edge_language_voice(config: Any, text: str, speed: float | None, voice: str | None = None) -> dict[str, Any]:
    next_config = dict(config) if isinstance(config, dict) else {}
    next_config["provider"] = "edge"

    edge_voice = voice or _EDGE_VOICE_BY_LANGUAGE.get(_detect_language_code(text))
    if edge_voice:
        _set_provider_option(next_config, "edge", "voice", edge_voice)
    if speed is not None:
        _set_provider_option(next_config, "edge", "speed", speed)
    return next_config


def _tts_config_with_elevenlabs_options(tts_tool: Any, config: Any, voice: str | None, speed: float | None) -> dict[str, Any]:
    next_config = dict(config) if isinstance(config, dict) else {}
    provider_config = next_config.get("elevenlabs") if isinstance(next_config.get("elevenlabs"), dict) else {}
    next_config["provider"] = "elevenlabs"
    _set_provider_option(
        next_config,
        "elevenlabs",
        "voice_id",
        voice or provider_config.get("voice_id") or getattr(tts_tool, "DEFAULT_ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB"),
    )
    _set_provider_option(
        next_config,
        "elevenlabs",
        "model_id",
        provider_config.get("model_id") or getattr(tts_tool, "DEFAULT_ELEVENLABS_STREAMING_MODEL_ID", "eleven_flash_v2_5"),
    )
    elevenlabs_speed = _elevenlabs_speed(speed)
    if elevenlabs_speed is not None:
        _set_provider_option(next_config, "elevenlabs", "speed", elevenlabs_speed)
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


def _elevenlabs_speed(speed: float | None) -> float | None:
    if speed is None or speed == 1:
        return None
    return max(0.7, min(1.2, float(speed)))


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
