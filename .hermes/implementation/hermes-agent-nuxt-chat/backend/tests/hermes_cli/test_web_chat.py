"""Tests for native web chat API endpoints."""

from __future__ import annotations

from datetime import datetime

import pytest


@pytest.fixture
def client(monkeypatch, _isolate_hermes_home):
    try:
        from starlette.testclient import TestClient
    except ImportError:
        pytest.skip("fastapi/starlette not installed")

    import hermes_state
    from hermes_constants import get_hermes_home
    from hermes_cli.web_server import app, _SESSION_HEADER_NAME, _SESSION_TOKEN

    monkeypatch.setattr(hermes_state, "DEFAULT_DB_PATH", get_hermes_home() / "state.db")

    test_client = TestClient(app)
    test_client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
    return test_client


def _assert_iso_timestamp(value: str):
    assert datetime.fromisoformat(value).tzinfo is not None


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
        "messageCount": 2,
        "createdAt": data["sessions"][0]["createdAt"],
        "updatedAt": data["sessions"][0]["updatedAt"],
    }
    _assert_iso_timestamp(data["sessions"][0]["createdAt"])
    _assert_iso_timestamp(data["sessions"][0]["updatedAt"])


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


def test_rejects_unsafe_session_limit(client):
    response = client.get("/api/web-chat/sessions?limit=101")

    assert response.status_code == 422


def test_returns_session_with_messages(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("session-detail", source="web-chat", model="test-model")
    db.append_message("session-detail", "user", "Can you help?")
    db.append_message("session-detail", "assistant", "Yes.", reasoning="Short reasoning")

    response = client.get("/api/web-chat/sessions/session-detail")

    assert response.status_code == 200
    data = response.json()
    assert data["session"]["id"] == "session-detail"
    assert data["session"]["messageCount"] == 2
    assert [message["role"] for message in data["messages"]] == ["user", "assistant"]
    assert data["messages"][0]["parts"] == [{"type": "text", "text": "Can you help?", "name": None, "status": None, "input": None, "output": None, "url": None, "mediaType": None, "approvalId": None}]
    assert data["messages"][1]["parts"][0]["type"] == "reasoning"
    assert data["messages"][1]["parts"][0]["text"] == "Short reasoning"
    assert data["messages"][1]["parts"][1]["text"] == "Yes."


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


def test_start_run_returns_ids_and_persists_messages(client, monkeypatch):
    import hermes_cli.web_chat as web_chat

    def fake_executor(context, emit):
        emit({"type": "message.delta", "content": "Done"})
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))

    response = client.post("/api/web-chat/runs", json={"input": "Say done"})
    assert response.status_code == 202
    data = response.json()
    assert data["sessionId"]
    assert data["runId"]

    with client.stream("GET", f"/api/web-chat/runs/{data['runId']}/events") as stream:
        body = stream.read().decode()

    assert "event: run.started" in body
    assert "event: message.delta" in body
    assert "event: message.completed" in body
    assert "event: run.completed" in body

    detail = client.get(f"/api/web-chat/sessions/{data['sessionId']}")
    assert [message["role"] for message in detail.json()["messages"]] == ["user", "assistant"]
    assert detail.json()["messages"][1]["parts"][0]["text"] == "Done"


def test_start_run_allows_duplicate_initial_titles(client, monkeypatch):
    import hermes_cli.web_chat as web_chat

    def fake_executor(context, emit):
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))

    first = client.post("/api/web-chat/runs", json={"input": "Repeatable title"})
    second = client.post("/api/web-chat/runs", json={"input": "Repeatable title"})

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["sessionId"] != second.json()["sessionId"]


def test_run_events_accept_session_token_query_for_eventsource(client, monkeypatch):
    import hermes_cli.web_chat as web_chat
    from hermes_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN

    def fake_executor(context, emit):
        emit({"type": "message.delta", "content": "Done"})
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))

    start = client.post("/api/web-chat/runs", json={"input": "Say done"}).json()
    del client.headers[_SESSION_HEADER_NAME]

    with client.stream("GET", f"/api/web-chat/runs/{start['runId']}/events?session_token={_SESSION_TOKEN}") as stream:
        body = stream.read().decode()

    assert "event: message.delta" in body
    assert "event: run.completed" in body


def test_stop_run_marks_active_run_as_stopping(client, monkeypatch):
    import time
    import hermes_cli.web_chat as web_chat

    def blocking_executor(context, emit):
        while not context.stop_requested.is_set():
            time.sleep(0.01)
        return ""

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(blocking_executor))
    start = client.post("/api/web-chat/runs", json={"input": "Wait"}).json()

    response = client.post(f"/api/web-chat/runs/{start['runId']}/stop")

    assert response.status_code == 200
    assert response.json() == {"runId": start["runId"], "stopped": True}
