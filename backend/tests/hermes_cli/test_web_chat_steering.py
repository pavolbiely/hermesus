from __future__ import annotations

import threading
import time

from web_chat_test_helpers import git_repo


def test_steer_run_calls_runtime_callback_persists_message_and_emits_event(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = git_repo(tmp_path)
    executor_started = threading.Event()
    release_executor = threading.Event()
    seen = {}

    def fake_executor(context, emit):
        def steer(text):
            seen["steer"] = text

        context.steer_agent = steer
        executor_started.set()
        assert release_executor.wait(timeout=2)
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))
    start = client.post("/api/web-chat/runs", json={"input": "Work", "workspace": str(repo)}).json()
    assert executor_started.wait(timeout=2)

    response = client.post(f"/api/web-chat/runs/{start['runId']}/steer", json={"text": "Use the simple path"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["runId"] == start["runId"]
    assert payload["sessionId"] == start["sessionId"]
    assert payload["accepted"] is True
    assert payload["messageId"]
    assert seen == {"steer": "Use the simple path"}

    release_executor.set()
    with client.stream("GET", f"/api/web-chat/runs/{start['runId']}/events") as stream:
        body = stream.read().decode()

    assert "event: run.steered" in body
    assert payload["messageId"] in body
    detail = client.get(f"/api/web-chat/sessions/{start['sessionId']}")
    assert [message["role"] for message in detail.json()["messages"]] == ["user", "system", "assistant"]
    steer_message = detail.json()["messages"][1]
    assert steer_message["parts"] == [
        {
            "type": "steer",
            "text": "Use the simple path",
            "name": None,
            "status": None,
            "input": None,
            "output": None,
            "url": None,
            "mediaType": None,
            "approvalId": None,
            "prompt": None,
            "changes": None,
            "attachments": None,
        }
    ]


def test_steer_run_returns_404_for_unknown_run(client):
    response = client.post("/api/web-chat/runs/missing/steer", json={"text": "hello"})

    assert response.status_code == 404


def test_steer_run_returns_409_when_runtime_cannot_steer(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = git_repo(tmp_path)
    executor_started = threading.Event()
    release_executor = threading.Event()

    def fake_executor(context, emit):
        executor_started.set()
        assert release_executor.wait(timeout=2)
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))
    start = client.post("/api/web-chat/runs", json={"input": "Work", "workspace": str(repo)}).json()
    assert executor_started.wait(timeout=2)

    response = client.post(f"/api/web-chat/runs/{start['runId']}/steer", json={"text": "hello"})

    assert response.status_code == 409
    release_executor.set()


def test_steer_run_returns_409_for_finished_run(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = git_repo(tmp_path)
    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(lambda context, emit: "Done"))
    start = client.post("/api/web-chat/runs", json={"input": "Work", "workspace": str(repo)}).json()

    with client.stream("GET", f"/api/web-chat/runs/{start['runId']}/events") as stream:
        stream.read()

    response = client.post(f"/api/web-chat/runs/{start['runId']}/steer", json={"text": "hello"})

    assert response.status_code == 409
