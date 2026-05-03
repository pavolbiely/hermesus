"""Tests for native web chat API endpoints."""

from __future__ import annotations

import json
import types

from web_chat_test_helpers import assert_iso_timestamp



def test_lists_sessions_for_chat_sidebar(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("session-alpha", source="cli", model="test-model")
    db.set_session_title("session-alpha", "Alpha title")
    db.append_message("session-alpha", "user", "Hello from the first session")
    db.append_message("session-alpha", "assistant", "Hi there")

    response = client.get("/api/web-chat/sessions")

    assert response.status_code == 200
    data = response.json()
    assert data["sessions"][0] == {
        "id": "session-alpha",
        "title": "Alpha title",
        "preview": "Hello from the first session",
        "source": "cli",
        "model": "test-model",
        "provider": None,
        "reasoningEffort": None,
        "workspace": None,
        "pinned": False,
        "archived": False,
        "messageCount": 2,
        "createdAt": data["sessions"][0]["createdAt"],
        "updatedAt": data["sessions"][0]["updatedAt"],
    }
    assert_iso_timestamp(data["sessions"][0]["createdAt"])
    assert_iso_timestamp(data["sessions"][0]["updatedAt"])


def test_synthesizes_speech_with_request_voice_override(client, tmp_path, monkeypatch):
    import tools.tts_tool as tts_tool

    audio_path = tmp_path / "speech.mp3"
    audio_path.write_bytes(b"fake mp3")
    seen_configs = []

    def load_config():
        return {"provider": "openai", "openai": {"voice": "alloy"}}

    def text_to_speech_tool(*, text):
        seen_configs.append(tts_tool._load_tts_config())
        assert text == "Hello"
        return json.dumps({"success": True, "file_path": str(audio_path)})

    monkeypatch.setattr(tts_tool, "_load_tts_config", load_config)
    monkeypatch.setattr(tts_tool, "text_to_speech_tool", text_to_speech_tool)

    response = client.post("/api/web-chat/tts", json={"text": "Hello", "voice": "nova", "speed": 1.25})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert response.content == b"fake mp3"
    assert seen_configs == [{"provider": "openai", "speed": 1.25, "openai": {"voice": "nova"}}]
    assert tts_tool._load_tts_config() == {"provider": "openai", "openai": {"voice": "alloy"}}


def test_transcribes_speech_input_with_elevenlabs_request_api_key(client, monkeypatch):
    import tools.tts_tool as tts_tool

    calls = []

    class FakeSpeechToText:
        def convert(self, **kwargs):
            calls.append(kwargs)
            return types.SimpleNamespace(text="hello from voice")

    class FakeElevenLabs:
        def __init__(self, *, api_key):
            calls.append({"api_key": api_key})
            self.speech_to_text = FakeSpeechToText()

    monkeypatch.setattr(tts_tool, "_import_elevenlabs", lambda: FakeElevenLabs)
    monkeypatch.setattr(tts_tool, "_load_tts_config", lambda: {"elevenlabs": {"stt_model_id": "scribe_v1"}})

    response = client.post(
        "/api/web-chat/speech-input/transcribe",
        data={"provider": "elevenlabs", "apiKey": "dummy-api-key"},
        files={"file": ("voice-input.webm", b"fake webm", "audio/webm")},
    )

    assert response.status_code == 200
    assert response.json() == {"text": "hello from voice", "provider": "elevenlabs"}
    assert calls == [
        {"api_key": "dummy-api-key"},
        {
            "file": ("voice-input.webm", b"fake webm", "audio/webm"),
            "model_id": "scribe_v1",
        },
    ]


def test_synthesized_speech_uses_server_cache(client, tmp_path, monkeypatch):
    import tools.tts_tool as tts_tool

    audio_path = tmp_path / "speech.mp3"
    audio_path.write_bytes(b"cached mp3")
    calls = 0

    def load_config():
        return {"provider": "edge", "edge": {"voice": "en-US-AriaNeural"}}

    def text_to_speech_tool(*, text):
        nonlocal calls
        calls += 1
        assert text == "Cache this response."
        return json.dumps({"success": True, "file_path": str(audio_path)})

    monkeypatch.setattr(tts_tool, "_load_tts_config", load_config)
    monkeypatch.setattr(tts_tool, "text_to_speech_tool", text_to_speech_tool)

    first = client.post("/api/web-chat/tts", json={"text": "Cache this response.", "speed": 1.25})
    audio_path.write_bytes(b"changed source should not be read")
    second = client.post("/api/web-chat/tts", json={"text": "Cache this response.", "speed": 1.25})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.content == b"cached mp3"
    assert second.content == b"cached mp3"
    assert calls == 1


def test_synthesized_speech_cache_varies_by_speed(client, tmp_path, monkeypatch):
    import tools.tts_tool as tts_tool

    calls = []

    def load_config():
        return {"provider": "edge", "edge": {"voice": "en-US-AriaNeural"}}

    def text_to_speech_tool(*, text):
        audio_path = tmp_path / f"speech-{len(calls)}.mp3"
        audio_path.write_bytes(f"fake mp3 {len(calls)}".encode())
        calls.append(text)
        return json.dumps({"success": True, "file_path": str(audio_path)})

    monkeypatch.setattr(tts_tool, "_load_tts_config", load_config)
    monkeypatch.setattr(tts_tool, "text_to_speech_tool", text_to_speech_tool)

    normal = client.post("/api/web-chat/tts", json={"text": "Same text, different speed.", "speed": 1})
    faster = client.post("/api/web-chat/tts", json={"text": "Same text, different speed.", "speed": 1.5})

    assert normal.status_code == 200
    assert faster.status_code == 200
    assert normal.content == b"fake mp3 0"
    assert faster.content == b"fake mp3 1"
    assert calls == ["Same text, different speed.", "Same text, different speed."]


def test_streams_edge_speech_and_reuses_server_cache(client, monkeypatch):
    import tools.tts_tool as tts_tool

    calls = []

    class FakeCommunicate:
        def __init__(self, text, *, voice, rate):
            calls.append({"text": text, "voice": voice, "rate": rate})

        async def stream(self):
            yield {"type": "audio", "data": b"streamed "}
            yield {"type": "WordBoundary"}
            yield {"type": "audio", "data": b"mp3"}

    monkeypatch.setattr(tts_tool, "_load_tts_config", lambda: {"provider": "edge"})
    monkeypatch.setitem(__import__("sys").modules, "edge_tts", types.SimpleNamespace(Communicate=FakeCommunicate))

    first = client.post("/api/web-chat/tts/stream", json={"text": "Stream this response.", "speed": 1.25})
    second = client.post("/api/web-chat/tts/stream", json={"text": "Stream this response.", "speed": 1.25})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.headers["content-type"].startswith("audio/mpeg")
    assert first.content == b"streamed mp3"
    assert second.content == b"streamed mp3"
    assert calls == [{"text": "Stream this response.", "voice": "en-US-BrianNeural", "rate": "+25%"}]


def test_streams_elevenlabs_speech_with_request_api_key_and_reuses_cache(client, monkeypatch):
    import tools.tts_tool as tts_tool

    calls = []

    class FakeTextToSpeech:
        def convert(self, **kwargs):
            calls.append(kwargs)
            yield b"eleven "
            yield b"mp3"

    class FakeElevenLabs:
        def __init__(self, *, api_key):
            calls.append({"api_key": api_key})
            self.text_to_speech = FakeTextToSpeech()

    monkeypatch.setattr(tts_tool, "_load_tts_config", lambda: {"elevenlabs": {"voice_id": "configured", "model_id": "eleven_flash_v2_5"}})
    monkeypatch.setattr(tts_tool, "_import_elevenlabs", lambda: FakeElevenLabs)

    payload = {"text": "Stream with ElevenLabs.", "provider": "elevenlabs", "apiKey": "secret", "voice": "voice-1", "speed": 1.25}
    first = client.post("/api/web-chat/tts/stream", json=payload)
    second = client.post("/api/web-chat/tts/stream", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.headers["content-type"].startswith("audio/mpeg")
    assert first.content == b"eleven mp3"
    assert second.content == b"eleven mp3"
    assert calls[0] == {"api_key": payload["apiKey"]}
    convert_call = calls[1]
    voice_settings = convert_call.pop("voice_settings")
    assert convert_call == {
        "text": "Stream with ElevenLabs.",
        "voice_id": "voice-1",
        "model_id": "eleven_flash_v2_5",
        "output_format": "mp3_44100_128",
    }
    assert getattr(voice_settings, "speed", None) == 1.2


def test_synthesizes_edge_speech_with_detected_language_voice(client, tmp_path, monkeypatch):
    import tools.tts_tool as tts_tool

    audio_path = tmp_path / "speech.mp3"
    audio_path.write_bytes(b"fake mp3")
    seen_configs = []

    def load_config():
        return {"provider": "openai", "openai": {"voice": "alloy"}}

    def text_to_speech_tool(*, text):
        seen_configs.append(tts_tool._load_tts_config())
        assert text == "This response should be read in English."
        return json.dumps({"success": True, "file_path": str(audio_path)})

    monkeypatch.setattr(tts_tool, "_load_tts_config", load_config)
    monkeypatch.setattr(tts_tool, "text_to_speech_tool", text_to_speech_tool)

    response = client.post("/api/web-chat/tts", json={"text": "This response should be read in English.", "speed": 1.5})

    assert response.status_code == 200
    assert response.content == b"fake mp3"
    assert seen_configs == [{
        "provider": "edge",
        "openai": {"voice": "alloy"},
        "edge": {"voice": "en-US-BrianNeural", "speed": 1.5},
    }]
    assert tts_tool._load_tts_config() == {"provider": "openai", "openai": {"voice": "alloy"}}


def test_synthesizes_edge_speech_with_slovak_language_voice(client, tmp_path, monkeypatch):
    import tools.tts_tool as tts_tool

    audio_path = tmp_path / "speech.mp3"
    audio_path.write_bytes(b"fake mp3")
    seen_configs = []

    def load_config():
        return {"provider": "edge", "edge": {"voice": "en-US-AriaNeural"}}

    def text_to_speech_tool(*, text):
        seen_configs.append(tts_tool._load_tts_config())
        assert text == "Toto je slovenská odpoveď."
        return json.dumps({"success": True, "file_path": str(audio_path)})

    monkeypatch.setattr(tts_tool, "_load_tts_config", load_config)
    monkeypatch.setattr(tts_tool, "text_to_speech_tool", text_to_speech_tool)

    response = client.post("/api/web-chat/tts", json={"text": "Toto je slovenská odpoveď."})

    assert response.status_code == 200
    assert response.content == b"fake mp3"
    assert seen_configs == [{"provider": "edge", "edge": {"voice": "sk-SK-LukasNeural"}}]
    assert tts_tool._load_tts_config() == {"provider": "edge", "edge": {"voice": "en-US-AriaNeural"}}


def test_returns_short_plain_read_aloud_text_without_llm(client, monkeypatch):
    import agent.auxiliary_client as auxiliary_client

    def call_llm(**_kwargs):
        raise AssertionError("short plain read-aloud text should not call an LLM")

    monkeypatch.setattr(auxiliary_client, "call_llm", call_llm)

    response = client.post(
        "/api/web-chat/read-aloud-summary",
        json={"text": "Testy prešli bez chýb."},
    )

    assert response.status_code == 200
    assert response.json() == {"text": "Testy prešli bez chýb."}


def test_generates_read_aloud_summary_for_multi_sentence_plain_text(client, monkeypatch):
    import agent.auxiliary_client as auxiliary_client

    calls = []

    def call_llm(**kwargs):
        calls.append(kwargs)
        message = types.SimpleNamespace(content="Stručne: upravil som nastavenia a testy prešli.")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    monkeypatch.setattr(auxiliary_client, "call_llm", call_llm)

    response = client.post(
        "/api/web-chat/read-aloud-summary",
        json={"text": "Upravil som nastavenia. Testy prešli bez chýb."},
    )

    assert response.status_code == 200
    assert response.json() == {"text": "Stručne: upravil som nastavenia a testy prešli."}
    assert len(calls) == 1


def test_generates_read_aloud_summary_with_auxiliary_llm(client, monkeypatch):
    import agent.auxiliary_client as auxiliary_client

    calls = []

    def call_llm(**kwargs):
        calls.append(kwargs)
        message = types.SimpleNamespace(
            content="Ľudsky prerozprávané: upravil som nastavenia čítania a overil som kontroly."
        )
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    monkeypatch.setattr(auxiliary_client, "call_llm", call_llm)

    response = client.post("/api/web-chat/read-aloud-summary", json={
        "text": "Updated `web/app/components/SettingsModal.vue`.\n```css\n.foo-bar-baz { color: red; }\n```\npnpm typecheck passed.",
        "model": "gpt-5.5",
        "provider": "openai-codex",
        "reasoningEffort": "low",
    })

    assert response.status_code == 200
    assert response.json() == {
        "text": "Ľudsky prerozprávané: upravil som nastavenia čítania a overil som kontroly."
    }
    assert calls[0]["task"] == "title_generation"
    assert calls[0]["provider"] == "openai-codex"
    assert calls[0]["model"] == "gpt-5.5"
    assert calls[0]["max_tokens"] == 2_000
    assert calls[0]["temperature"] == 0.2
    assert calls[0]["timeout"] == 90
    prompt = calls[0]["messages"][0]["content"]
    assert "Fast task" in prompt
    assert "Do not browse, inspect files, run tools, execute commands, read history, or gather extra context" in prompt
    assert "Use only the text provided" in prompt
    assert "human, listenable spoken retelling" in prompt
    assert "Do not narrate the message line by line" in prompt
    assert "Retell it like a helpful person speaking naturally" in prompt
    assert "compress repetitive or low-value detail" in prompt
    assert "Do not read raw code" in prompt
    assert "SettingsModal.vue" in prompt


def test_generates_read_aloud_summary_with_hidden_agent_fallback(client, monkeypatch):
    from hermes_cli import web_chat
    import hermes_cli.web_chat_modules.read_aloud_summaries as read_aloud_summaries

    calls = []

    def hidden_agent(prompt, *, conversation_history, **kwargs):
        calls.append({"prompt": prompt, "conversation_history": conversation_history, "kwargs": kwargs})
        return "Fallback summary"

    def unavailable_auxiliary(_prompt, **_kwargs):
        raise ImportError("no auxiliary client")

    monkeypatch.setattr(read_aloud_summaries, "_generate_summary_with_auxiliary_llm", unavailable_auxiliary)
    monkeypatch.setattr(web_chat, "_hidden_session_summary_agent", hidden_agent)

    response = client.post(
        "/api/web-chat/read-aloud-summary",
        json={
            "text": "Updated `file.py` after a long assistant response",
            "model": "gpt-5.5",
            "provider": "openai-codex",
            "reasoningEffort": "low",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"text": "Fallback summary"}
    assert calls[0]["conversation_history"] == []
    assert calls[0]["kwargs"] == {
        "model": "gpt-5.5",
        "provider": "openai-codex",
        "reasoning_effort": "low",
    }


def test_generates_read_aloud_summary_with_hidden_agent_when_auxiliary_returns_empty(client, monkeypatch):
    from hermes_cli import web_chat
    import agent.auxiliary_client as auxiliary_client

    calls = []

    def call_llm(**_kwargs):
        message = types.SimpleNamespace(content="")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    def hidden_agent(prompt, *, conversation_history, **kwargs):
        calls.append({"prompt": prompt, "conversation_history": conversation_history, "kwargs": kwargs})
        return "Fallback after empty auxiliary summary"

    monkeypatch.setattr(auxiliary_client, "call_llm", call_llm)
    monkeypatch.setattr(web_chat, "_hidden_session_summary_agent", hidden_agent)

    response = client.post(
        "/api/web-chat/read-aloud-summary",
        json={
            "text": "Updated `file.py` after a long assistant response",
            "model": "gpt-5.5",
            "provider": "openai-codex",
            "reasoningEffort": "low",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"text": "Fallback after empty auxiliary summary"}
    assert calls[0]["conversation_history"] == []
    assert calls[0]["kwargs"] == {
        "model": "gpt-5.5",
        "provider": "openai-codex",
        "reasoning_effort": "low",
    }


def test_session_preview_reports_missing_summary(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("preview-missing", source="web-chat")
    db.append_message("preview-missing", "user", "What is this chat about?")

    response = client.get("/api/web-chat/sessions/preview-missing/preview")

    assert response.status_code == 200
    assert response.json() == {
        "sessionId": "preview-missing",
        "summary": None,
        "summaryStatus": "missing",
        "messageCount": 1,
        "updatedAt": None,
    }


def test_generates_session_preview_outside_chat_history(client, monkeypatch):
    from hermes_cli import web_chat
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("preview-generate", source="web-chat", model="test-model")
    db.append_message("preview-generate", "user", "Implement a sidebar popover")
    db.append_message("preview-generate", "assistant", "Implemented cached chat previews")
    calls = []

    def hidden_agent(prompt, *, conversation_history, **kwargs):
        calls.append({"prompt": prompt, "conversation_history": conversation_history, "kwargs": kwargs})
        return "Chat rieši sidebar preview sumarizáciu cez cacheovaný out-of-band Hermes prompt."

    monkeypatch.setattr(web_chat, "_hidden_session_summary_agent", hidden_agent)

    response = client.post("/api/web-chat/sessions/preview-generate/preview-summary")

    assert response.status_code == 200
    data = response.json()
    assert data["summaryStatus"] == "ready"
    assert data["summary"] == "Chat rieši sidebar preview sumarizáciu cez cacheovaný out-of-band Hermes prompt."
    assert data["messageCount"] == 2
    assert len(db.get_messages("preview-generate")) == 2
    assert calls[0]["conversation_history"] == [
        {"role": "user", "content": "Implement a sidebar popover"},
        {"role": "assistant", "content": "Implemented cached chat previews"},
    ]
    stored_config = db.get_session("preview-generate")["model_config"]
    if isinstance(stored_config, str):
        stored_config = json.loads(stored_config)
    stored = stored_config["sidebar_summary"]
    assert stored["text"] == data["summary"]
    assert stored["source"] == "hidden_hermes"
    assert_iso_timestamp(stored["updatedAt"])


def test_omits_empty_sessions_from_chat_sidebar(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("empty-session", source="web-chat")
    db.create_session("populated-session", source="web-chat")
    db.append_message("populated-session", "user", "Keep this one")

    response = client.get("/api/web-chat/sessions")

    assert response.status_code == 200
    session_ids = [session["id"] for session in response.json()["sessions"]]
    assert "populated-session" in session_ids
    assert "empty-session" not in session_ids


def test_lists_sidebar_sessions_by_last_message_timestamp(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("newer-session", source="web-chat")
    db.create_session("older-session-with-newer-message", source="web-chat")
    db.append_message("newer-session", "user", "Started later")
    db.append_message("older-session-with-newer-message", "user", "Updated later")

    def set_timestamps(conn):
        conn.execute("UPDATE sessions SET started_at = ? WHERE id = ?", (200.0, "newer-session"))
        conn.execute("UPDATE sessions SET started_at = ? WHERE id = ?", (100.0, "older-session-with-newer-message"))
        conn.execute("UPDATE messages SET timestamp = ? WHERE session_id = ?", (250.0, "newer-session"))
        conn.execute("UPDATE messages SET timestamp = ? WHERE session_id = ?", (300.0, "older-session-with-newer-message"))

    db._execute_write(set_timestamps)

    response = client.get("/api/web-chat/sessions")

    assert response.status_code == 200
    assert [session["id"] for session in response.json()["sessions"]] == [
        "older-session-with-newer-message",
        "newer-session",
    ]


def test_lists_pinned_sidebar_sessions_first(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("newer-unpinned", source="web-chat")
    db.create_session("older-pinned", source="web-chat", model_config={"pinned": True})
    db.append_message("newer-unpinned", "user", "Updated later")
    db.append_message("older-pinned", "user", "Pinned")

    def set_timestamps(conn):
        conn.execute("UPDATE messages SET timestamp = ? WHERE session_id = ?", (300.0, "newer-unpinned"))
        conn.execute("UPDATE messages SET timestamp = ? WHERE session_id = ?", (100.0, "older-pinned"))

    db._execute_write(set_timestamps)

    response = client.get("/api/web-chat/sessions")

    assert response.status_code == 200
    sessions = response.json()["sessions"]
    assert [session["id"] for session in sessions] == ["older-pinned", "newer-unpinned"]
    assert sessions[0]["pinned"] is True
    assert sessions[1]["pinned"] is False


def test_compressed_sidebar_session_uses_tip_workspace(client, tmp_path):
    from hermes_state import SessionDB

    root_workspace = tmp_path / "root-workspace"
    tip_workspace = tmp_path / "tip-workspace"
    root_workspace.mkdir()
    tip_workspace.mkdir()

    db = SessionDB()
    db.create_session("root-session", source="web-chat", model_config={"workspace": str(root_workspace)})
    db.append_message("root-session", "user", "Before compression")
    db.end_session("root-session", "compression")
    db.create_session(
        "tip-session",
        source="web-chat",
        model_config={"workspace": str(tip_workspace)},
        parent_session_id="root-session",
    )
    db.append_message("tip-session", "user", "After compression")

    response = client.get("/api/web-chat/sessions")

    assert response.status_code == 200
    sessions = response.json()["sessions"]
    assert sessions[0]["id"] == "tip-session"
    assert sessions[0]["workspace"] == str(tip_workspace)


def test_session_detail_reports_compression_count(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("root-session", source="web-chat")
    db.append_message("root-session", "user", "Before compression")
    db.end_session("root-session", "compression")
    db.create_session("second-session", source="web-chat", parent_session_id="root-session")
    db.append_message("second-session", "user", "After first compression")
    db.end_session("second-session", "compression")
    db.create_session("third-session", source="web-chat", parent_session_id="second-session")
    db.append_message("third-session", "user", "After second compression")

    response = client.get("/api/web-chat/sessions/third-session")

    assert response.status_code == 200
    data = response.json()
    assert data["compressionCount"] == 2
    assert [message["parts"][0]["text"] for message in data["messages"]] == [
        "Before compression",
        "After first compression",
        "After second compression",
    ]
    assert data["messagesTotal"] == 3


def test_agent_history_includes_compressed_parent_messages(client):
    from hermes_cli.web_chat_modules.agent_runner import conversation_history_for_agent
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("root-session", source="web-chat")
    db.append_message("root-session", "user", "Before compression")
    db.append_message("root-session", "assistant", "Root answer")
    db.end_session("root-session", "compression")
    db.create_session("tip-session", source="web-chat", parent_session_id="root-session")
    db.append_message("tip-session", "user", "Latest prompt")

    history = conversation_history_for_agent(lambda: db, "tip-session")

    assert history == [
        {"role": "user", "content": "Before compression"},
        {"role": "assistant", "content": "Root answer"},
    ]


def test_rejects_unsafe_session_limit(client):
    response = client.get("/api/web-chat/sessions?limit=101")

    assert response.status_code == 422


def test_returns_session_with_messages(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("session-detail", source="web-chat", model="test-model")
    db.append_message("session-detail", "user", "Can you help?", token_count=4)
    db.append_message(
        "session-detail",
        "assistant",
        "Yes.",
        reasoning="Short reasoning",
        token_count=128,
        codex_message_items=[{"type": "web_chat_metrics", "metrics": {
            "tokenCount": 128,
            "inputTokens": 50,
            "outputTokens": 60,
            "cacheReadTokens": 5,
            "reasoningTokens": 13,
            "apiCalls": 2,
            "generationDurationMs": 2500,
            "modelDurationMs": 2000,
            "toolDurationMs": 400,
            "promptWaitDurationMs": 100,
        }}],
    )

    response = client.get("/api/web-chat/sessions/session-detail")

    assert response.status_code == 200
    data = response.json()
    assert data["session"]["id"] == "session-detail"
    assert data["session"]["messageCount"] == 2
    assert data["session"]["reasoningEffort"] is None
    assert [message["role"] for message in data["messages"]] == ["user", "assistant"]
    assert [message["tokenCount"] for message in data["messages"]] == [55, 128]
    assert data["messages"][0]["inputTokens"] == 50
    assert data["messages"][1]["outputTokens"] == 60
    assert data["messages"][1]["reasoningTokens"] == 13
    assert data["messages"][1]["apiCalls"] == 2
    assert data["messages"][1]["generationDurationMs"] == 2500
    assert data["messages"][1]["modelDurationMs"] == 2000
    assert data["messages"][1]["toolDurationMs"] == 400
    assert data["messages"][1]["promptWaitDurationMs"] == 100
    user_text_part = data["messages"][0]["parts"][0]
    assert user_text_part["type"] == "text"
    assert user_text_part["text"] == "Can you help?"
    assert data["messages"][1]["parts"][0]["type"] == "reasoning"
    assert data["messages"][1]["parts"][0]["text"] == "Short reasoning"
    assert data["messages"][1]["parts"][1]["text"] == "Yes."


def test_gets_session_detail_message_window(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("session-window", source="web-chat")
    message_ids = []
    for index in range(5):
        message_ids.append(db.append_message("session-window", "user", f"Message {index}"))

    response = client.get("/api/web-chat/sessions/session-window?messageLimit=2")

    assert response.status_code == 200
    data = response.json()
    assert data["messagesTotal"] == 5
    assert data["messagesHasMoreBefore"] is True
    assert [message["parts"][0]["text"] for message in data["messages"]] == ["Message 3", "Message 4"]

    older = client.get(f"/api/web-chat/sessions/session-window?messageLimit=2&messageBefore={message_ids[3]}")

    assert older.status_code == 200
    older_data = older.json()
    assert older_data["messagesHasMoreBefore"] is True
    assert [message["parts"][0]["text"] for message in older_data["messages"]] == ["Message 1", "Message 2"]

    oldest = client.get(f"/api/web-chat/sessions/session-window?messageLimit=2&messageBefore={message_ids[1]}")

    assert oldest.status_code == 200
    oldest_data = oldest.json()
    assert oldest_data["messagesHasMoreBefore"] is False
    assert [message["parts"][0]["text"] for message in oldest_data["messages"]] == ["Message 0"]



def test_attaches_tool_output_to_tool_call_part(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("session-tools", source="web-chat", model="test-model")
    db.append_message("session-tools", "user", "Find files")
    db.append_message(
        "session-tools",
        "assistant",
        None,
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "search_files",
                    "arguments": "{\"query\":\"package.json\"}",
                },
            }
        ],
    )
    db.append_message(
        "session-tools",
        "tool",
        json.dumps({
            "total_count": 1,
            "files": ["/workspace/hermesum/web/package.json"],
        }),
        tool_call_id="call_1",
        tool_name="search_files",
    )

    response = client.get("/api/web-chat/sessions/session-tools")

    assert response.status_code == 200
    data = response.json()
    assert [message["role"] for message in data["messages"]] == ["user", "assistant"]
    tool_part = data["messages"][1]["parts"][0]
    assert tool_part["type"] == "tool"
    assert tool_part["name"] == "search_files"
    assert tool_part["input"]["id"] == "call_1"
    assert tool_part["output"] == {
        "total_count": 1,
        "files": ["/workspace/hermesum/web/package.json"],
    }



def test_creates_session_with_initial_user_message(client):
    response = client.post(
        "/api/web-chat/sessions",
        json={"message": "Build a Nuxt chat UI for Hermes Agent"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["session"]["id"]
    assert data["session"]["source"] == "web-chat"
    assert data["session"]["title"] == "Build a Nuxt chat UI for Hermes Agent"
    assert data["session"]["messageCount"] == 1
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["parts"][0]["text"] == "Build a Nuxt chat UI for Hermes Agent"

    detail = client.get(f"/api/web-chat/sessions/{data['session']['id']}")
    assert detail.status_code == 200
    assert detail.json()["messages"][0]["parts"][0]["text"] == "Build a Nuxt chat UI for Hermes Agent"



def test_renames_session_title(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("session-rename", source="web-chat")
    db.set_session_title("session-rename", "Old title")
    db.append_message("session-rename", "user", "Hello")

    response = client.patch("/api/web-chat/sessions/session-rename", json={"title": "New title"})

    assert response.status_code == 200
    assert response.json()["session"]["title"] == "New title"
    assert db.get_session("session-rename")["title"] == "New title"


def test_compressed_chat_keeps_root_title_visible(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("root-session", source="web-chat")
    db.set_session_title("root-session", "Loyalty program: konfigurátor")
    db.append_message("root-session", "user", "Start loyalty config")
    db.end_session("root-session", "compression")
    db.create_session("tip-session", source="web-chat", parent_session_id="root-session")
    db.set_session_title("tip-session", "Loyalty program: konfigurátor #2")
    db.append_message("tip-session", "assistant", "Continuing after compression")

    listed = client.get("/api/web-chat/sessions")
    detail = client.get("/api/web-chat/sessions/tip-session")

    assert listed.status_code == 200
    assert listed.json()["sessions"][0]["id"] == "tip-session"
    assert listed.json()["sessions"][0]["title"] == "Loyalty program: konfigurátor"
    assert detail.status_code == 200
    assert detail.json()["session"]["title"] == "Loyalty program: konfigurátor"


def test_renames_compressed_chat_root_title_from_tip_session(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("root-session", source="web-chat")
    db.set_session_title("root-session", "Loyalty program: konfigurátor")
    db.append_message("root-session", "user", "Start loyalty config")
    db.end_session("root-session", "compression")
    db.create_session("tip-session", source="web-chat", parent_session_id="root-session")
    db.set_session_title("tip-session", "Loyalty program: konfigurátor #2")
    db.append_message("tip-session", "assistant", "Continuing after compression")

    response = client.patch("/api/web-chat/sessions/tip-session", json={"title": "Loyalty configurator"})

    assert response.status_code == 200
    assert response.json()["session"]["id"] == "tip-session"
    assert response.json()["session"]["title"] == "Loyalty configurator"
    assert db.get_session("root-session")["title"] == "Loyalty configurator"
    assert db.get_session("tip-session")["title"] == "Loyalty program: konfigurátor #2"


def test_pins_and_unpins_session(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("session-pin", source="web-chat")
    db.append_message("session-pin", "user", "Pin me")

    pinned = client.patch("/api/web-chat/sessions/session-pin", json={"pinned": True})
    unpinned = client.patch("/api/web-chat/sessions/session-pin", json={"pinned": False})

    assert pinned.status_code == 200
    assert pinned.json()["session"]["pinned"] is True
    assert unpinned.status_code == 200
    assert unpinned.json()["session"]["pinned"] is False


def test_archives_and_restores_session(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("session-archive", source="web-chat")
    db.create_session("newer-session", source="web-chat")
    db.append_message("session-archive", "user", "Archive me")
    db.append_message("newer-session", "user", "Newer chat")

    def set_timestamps(conn):
        conn.execute("UPDATE messages SET timestamp = ? WHERE session_id = ?", (100.0, "session-archive"))
        conn.execute("UPDATE messages SET timestamp = ? WHERE session_id = ?", (200.0, "newer-session"))

    db._execute_write(set_timestamps)

    archived = client.patch("/api/web-chat/sessions/session-archive", json={"archived": True})
    default_list = client.get("/api/web-chat/sessions")
    archived_list = client.get("/api/web-chat/sessions?includeArchived=true")
    restored = client.patch("/api/web-chat/sessions/session-archive", json={"archived": False})
    restored_list = client.get("/api/web-chat/sessions")

    assert archived.status_code == 200
    assert archived.json()["session"]["archived"] is True
    assert [session["id"] for session in default_list.json()["sessions"]] == ["newer-session"]
    assert archived_list.json()["sessions"][1]["id"] == "session-archive"
    assert archived_list.json()["sessions"][1]["archived"] is True
    assert restored.status_code == 200
    assert restored.json()["session"]["archived"] is False
    assert restored_list.json()["sessions"][0]["id"] == "session-archive"
    assert db.get_session("session-archive") is not None


def test_restore_session_requires_existing_workspace(client, tmp_path):
    from hermes_state import SessionDB

    missing_workspace = tmp_path / "missing"
    target_workspace = tmp_path / "target"
    target_workspace.mkdir()
    create_workspace = client.post("/api/web-chat/workspaces", json={"label": "Target", "path": str(target_workspace)})
    assert create_workspace.status_code == 201

    db = SessionDB()
    db.create_session(
        "session-restore-missing-workspace",
        source="web-chat",
        model_config={"archived": True, "workspace": str(missing_workspace)},
    )
    db.append_message("session-restore-missing-workspace", "user", "Restore me")

    missing = client.patch("/api/web-chat/sessions/session-restore-missing-workspace", json={"archived": False})
    restored = client.patch(
        "/api/web-chat/sessions/session-restore-missing-workspace",
        json={"archived": False, "workspace": str(target_workspace)},
    )

    assert missing.status_code == 409
    assert missing.json()["detail"] == "Workspace no longer exists. Choose another workspace to restore this chat."
    assert restored.status_code == 200
    assert restored.json()["session"]["archived"] is False
    assert restored.json()["session"]["workspace"] == str(target_workspace)


def test_deletes_session(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("session-delete", source="web-chat")
    db.append_message("session-delete", "user", "Delete me")

    response = client.delete("/api/web-chat/sessions/session-delete")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert db.get_session("session-delete") is None


def test_duplicates_session_and_messages(client, tmp_path):
    import hermes_cli.web_chat as web_chat
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("session-copy", source="web-chat", model="test-model", model_config={"reasoningEffort": "high", "workspace": str(tmp_path)})
    db.set_session_title("session-copy", "Original title")
    db.append_message("session-copy", "user", "Question")
    assistant_message_id = db.append_message("session-copy", "assistant", "Answer", reasoning="Because")
    web_chat._record_session_git_changes(
        db,
        session_id="session-copy",
        run_id="run-copy",
        message_id=assistant_message_id,
        workspace=str(tmp_path),
        baseline_status="",
        final_status=" M changed.txt",
        changes=web_chat.WebChatWorkspaceChanges(
            files=[web_chat.WebChatFileChange(path="changed.txt", status="edited", additions=1, deletions=0)],
            totalFiles=1,
            totalAdditions=1,
            totalDeletions=0,
            workspace=str(tmp_path),
            runId="run-copy",
            patch={"files": [{"path": "changed.txt", "status": "edited", "patch": "@@ -1 +1 @@\n-old\n+new\n"}]},
            patchTruncated=False,
        ),
    )

    response = client.post("/api/web-chat/sessions/session-copy/duplicate")

    assert response.status_code == 201
    data = response.json()
    assert data["session"]["id"] != "session-copy"
    assert data["session"]["title"] == "Original title copy"
    assert data["session"]["source"] == "web-chat"
    assert data["session"]["model"] == "test-model"
    assert data["session"]["reasoningEffort"] == "high"
    assert data["session"]["workspace"] == str(tmp_path)
    assert [message["role"] for message in data["messages"]] == ["user", "assistant"]
    assert data["messages"][0]["parts"][0]["text"] == "Question"
    assert data["messages"][1]["parts"][0]["type"] == "reasoning"
    assert data["messages"][1]["parts"][1]["text"] == "Answer"
    assert data["messages"][1]["parts"][2]["type"] == "changes"
    assert data["messages"][1]["parts"][2]["changes"]["files"] == [
        {"path": "changed.txt", "status": "edited", "additions": 1, "deletions": 0}
    ]
    assert "+new" in data["messages"][1]["parts"][2]["changes"]["patch"]["files"][0]["patch"]

def test_edit_user_message_updates_content_and_deletes_following_history(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("session-edit", source="web-chat")
    first_id = db.append_message("session-edit", "user", "Original prompt")
    db.append_message("session-edit", "assistant", "Old answer")
    db.append_message("session-edit", "user", "Follow-up")

    response = client.patch(
        f"/api/web-chat/sessions/session-edit/messages/{first_id}",
        json={"content": "Edited prompt"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["session"]["messageCount"] == 1
    assert [part["text"] for message in data["messages"] for part in message["parts"] if part["type"] == "text"] == ["Edited prompt"]

    persisted = db.get_messages("session-edit")
    assert len(persisted) == 1
    assert persisted[0]["id"] == first_id
    assert persisted[0]["content"] == "Edited prompt"


def test_edit_archived_session_message_is_rejected(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("session-edit-archived", source="web-chat", model_config={"archived": True})
    message_id = db.append_message("session-edit-archived", "user", "Original")

    response = client.patch(
        f"/api/web-chat/sessions/session-edit-archived/messages/{message_id}",
        json={"content": "Edited"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Restore archived chat before editing a message."


def test_start_run_for_archived_session_is_rejected(client, monkeypatch):
    import hermes_cli.web_chat as web_chat
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("session-run-archived", source="web-chat", model_config={"archived": True})
    db.append_message("session-run-archived", "user", "Original")
    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(lambda context, emit: "Done"))

    response = client.post("/api/web-chat/runs", json={"sessionId": "session-run-archived", "input": "Continue"})

    assert response.status_code == 409
    assert response.json()["detail"] == "Restore archived chat before sending a message."


def test_edit_message_rejects_non_user_messages(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("session-edit", source="web-chat")
    assistant_id = db.append_message("session-edit", "assistant", "Cannot edit")

    response = client.patch(
        f"/api/web-chat/sessions/session-edit/messages/{assistant_id}",
        json={"content": "Edited"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only user messages can be edited."
