"""Tests for web-chat slash command endpoints."""

from __future__ import annotations

import subprocess

from web_chat_test_helpers import git_repo


def test_lists_safe_web_chat_commands(client):
    response = client.get("/api/web-chat/commands")

    assert response.status_code == 200
    data = response.json()
    command_ids = [command["id"] for command in data["commands"]]
    assert command_ids == [
        "clear",
        "title",
        "rollback",
        "status",
        "profile",
        "model",
        "provider",
        "personality",
        "reasoning",
        "fast",
        "voice",
        "help",
        "usage",
        "debug",
        "changes",
    ]
    assert len(command_ids) == len(set(command_ids))

    help_command = next(command for command in data["commands"] if command["id"] == "help")
    assert help_command == {
        "id": "help",
        "name": "/help",
        "description": "Show available slash commands.",
        "usage": "/help",
        "safety": "safe",
        "requiresWorkspace": False,
        "requiresSession": False,
    }
    clear = next(command for command in data["commands"] if command["id"] == "clear")
    assert clear["safety"] == "confirmation_required"
    changes = next(command for command in data["commands"] if command["id"] == "changes")
    assert changes["requiresWorkspace"] is True
    model = next(command for command in data["commands"] if command["id"] == "model")
    assert model["usage"] == "/model [model] [--provider name] [--global]"
    reasoning = next(command for command in data["commands"] if command["id"] == "reasoning")
    assert reasoning["usage"] == "/reasoning [level|show|hide]"
    rollback = next(command for command in data["commands"] if command["id"] == "rollback")
    assert rollback["usage"] == "/rollback [number]"


def test_executes_help_command_without_starting_agent(client):
    response = client.post("/api/web-chat/commands/execute", json={"command": "/help"})

    assert response.status_code == 200
    data = response.json()
    assert data["commandId"] == "help"
    assert data["handled"] is True
    assert data["message"]["role"] == "assistant"
    help_text = data["message"]["parts"][0]["text"]
    assert "Available slash commands" in help_text
    assert "/model [model] [--provider name] [--global]" in help_text


def test_executes_status_command(client, tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()

    response = client.post("/api/web-chat/commands/execute", json={
        "command": "/status",
        "workspace": str(workspace),
        "model": "gpt-test",
        "reasoningEffort": "medium",
    })

    assert response.status_code == 200
    text = response.json()["message"]["parts"][0]["text"]
    assert str(workspace.resolve()) in text
    assert "gpt-test" in text
    assert "medium" in text


def test_rejects_unknown_slash_command(client):
    response = client.post("/api/web-chat/commands/execute", json={"command": "/rm -rf /"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Command not found"


def test_rejects_confirmation_required_command_without_confirmation(client):
    response = client.post("/api/web-chat/commands/execute", json={"command": "/clear", "sessionId": "abc"})

    assert response.status_code == 409
    assert response.json()["detail"] == "This command requires confirmation."


def test_persists_command_response_when_session_is_provided(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("session-command", source="web-chat")
    db.append_message("session-command", "user", "Existing prompt")

    response = client.post("/api/web-chat/commands/execute", json={"command": "/help", "sessionId": "session-command"})

    assert response.status_code == 200
    assert response.json()["sessionId"] == "session-command"

    detail = client.get("/api/web-chat/sessions/session-command")
    messages = detail.json()["messages"]
    assert [message["role"] for message in messages][-2:] == ["user", "assistant"]
    assert messages[-2]["parts"][0]["text"] == "/help"
    assert "Available slash commands" in messages[-1]["parts"][0]["text"]


def test_command_without_session_creates_persisted_chat(client):
    response = client.post("/api/web-chat/commands/execute", json={"command": "/help"})

    assert response.status_code == 200
    session_id = response.json()["sessionId"]
    assert session_id

    detail = client.get(f"/api/web-chat/sessions/{session_id}")
    assert detail.status_code == 200
    messages = detail.json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["parts"][0]["text"] == "/help"
    assert "Available slash commands" in messages[1]["parts"][0]["text"]


def test_executes_changes_command_with_workspace(client, tmp_path):
    repo = git_repo(tmp_path)
    (repo / "tracked.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    (repo / "tracked.txt").write_text("one\ntwo\n", encoding="utf-8")

    response = client.post("/api/web-chat/commands/execute", json={"command": "/changes", "workspace": str(repo)})

    assert response.status_code == 200
    data = response.json()
    assert data["commandId"] == "changes"
    assert data["changes"]["files"] == [
        {"path": "tracked.txt", "status": "edited", "additions": 1, "deletions": 0}
    ]


def test_persists_changes_command_response_and_changes(client, tmp_path):
    from hermes_state import SessionDB

    repo = git_repo(tmp_path)
    (repo / "tracked.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    (repo / "tracked.txt").write_text("one\ntwo\n", encoding="utf-8")
    db = SessionDB()
    db.create_session("session-command-changes", source="web-chat", model_config={"workspace": str(repo)})

    response = client.post(
        "/api/web-chat/commands/execute",
        json={"command": "/changes", "sessionId": "session-command-changes", "workspace": str(repo)},
    )

    assert response.status_code == 200
    detail = client.get("/api/web-chat/sessions/session-command-changes?includeWorkspaceChanges=true")
    messages = detail.json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["parts"][0]["text"] == "/changes"
    assert messages[1]["parts"][0]["text"] == "Workspace changes:"
    assert messages[1]["parts"][1]["type"] == "changes"
    assert messages[1]["parts"][1]["changes"]["files"] == [
        {"path": "tracked.txt", "status": "edited", "additions": 1, "deletions": 0}
    ]


def test_changes_command_requires_workspace(client):
    response = client.post("/api/web-chat/commands/execute", json={"command": "/changes"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Select a workspace before running /changes."

