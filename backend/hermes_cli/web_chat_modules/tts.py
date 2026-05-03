"""Text-to-speech helpers for web-chat response read-aloud."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from fastapi.responses import FileResponse

_MEDIA_TYPES = {
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
}

_TTS_CONFIG_OVERRIDE_LOCK = threading.Lock()
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

    return FileResponse(
        file_path,
        media_type=_MEDIA_TYPES.get(file_path.suffix.lower(), "application/octet-stream"),
        filename=file_path.name,
        content_disposition_type="inline",
    )


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
