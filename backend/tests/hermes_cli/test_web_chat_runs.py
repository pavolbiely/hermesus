"""Tests for web chat run lifecycle endpoints."""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

from web_chat_test_helpers import git_repo


def test_start_run_returns_ids_and_persists_messages(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    seen = {}

    def fake_executor(context, emit):
        seen["model"] = context.model
        seen["reasoningEffort"] = context.reasoning_effort
        seen["workspace"] = context.workspace
        emit({"type": "message.delta", "content": "Done"})
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))

    response = client.post("/api/web-chat/runs", json={
        "input": "Say done",
        "model": "gpt-5.3-codex",
        "reasoningEffort": "high",
        "workspace": str(repo),
        "clientMessageId": "client-message-1",
    })
    assert response.status_code == 202
    data = response.json()
    assert data["sessionId"]
    assert data["runId"]
    assert data["userMessageId"]
    assert seen == {"model": "gpt-5.3-codex", "reasoningEffort": "high", "workspace": str(repo)}

    with client.stream("GET", f"/api/web-chat/runs/{data['runId']}/events") as stream:
        body = stream.read().decode()

    assert "event: run.started" in body
    assert "event: message.delta" in body
    assert "event: message.completed" in body
    assert "event: run.completed" in body

    detail = client.get(f"/api/web-chat/sessions/{data['sessionId']}")
    assert [message["role"] for message in detail.json()["messages"]] == ["user", "assistant"]
    assert detail.json()["messages"][0]["id"] == data["userMessageId"]
    assert detail.json()["messages"][0]["clientMessageId"] == "client-message-1"
    assert detail.json()["messages"][1]["parts"][0]["text"] == "Done"
    assert detail.json()["session"]["model"] == "gpt-5.3-codex"
    assert detail.json()["session"]["reasoningEffort"] == "high"
    assert detail.json()["session"]["workspace"] == str(repo)


def test_start_run_streams_agent_status_without_persisting_status(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = git_repo(tmp_path)

    def fake_executor(context, emit):
        emit({
            "type": "agent.status",
            "kind": "warn",
            "message": "test warning",
            "createdAt": "2026-04-27T12:00:00+00:00",
        })
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))

    response = client.post("/api/web-chat/runs", json={"input": "Say done", "workspace": str(repo)})
    assert response.status_code == 202
    run = response.json()

    with client.stream("GET", f"/api/web-chat/runs/{run['runId']}/events") as stream:
        body = stream.read().decode()

    assert "event: agent.status" in body
    assert "test warning" in body
    assert "event: message.completed" in body

    detail = client.get(f"/api/web-chat/sessions/{run['sessionId']}")
    messages = detail.json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["parts"][0]["text"] == "Done"
    assert "test warning" not in json.dumps(messages)


def test_stop_run_interrupts_executor_and_persists_interrupted_message(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    executor_started = threading.Event()
    seen = {}

    def fake_executor(context, emit):
        def interrupt(message=None):
            seen["interrupt"] = message
            context.stop_requested.set()

        context.interrupt_agent = interrupt
        executor_started.set()
        assert context.stop_requested.wait(timeout=2)
        return "Should not be persisted"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))

    response = client.post("/api/web-chat/runs", json={"input": "Keep going", "workspace": str(repo)})
    assert response.status_code == 202
    run = response.json()
    assert executor_started.wait(timeout=2)

    stop = client.post(f"/api/web-chat/runs/{run['runId']}/stop")
    assert stop.status_code == 200
    assert stop.json() == {"runId": run["runId"], "stopped": True}
    assert seen["interrupt"] == "Chat interrupted by user"

    with client.stream("GET", f"/api/web-chat/runs/{run['runId']}/events") as stream:
        body = stream.read().decode()

    assert "event: message.completed" in body
    assert "Chat interrupted." in body
    assert "event: run.stopped" in body
    assert "Should not be persisted" not in body

    detail = client.get(f"/api/web-chat/sessions/{run['sessionId']}")
    messages = detail.json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["parts"][0]["text"] == "Chat interrupted."


def test_start_run_persists_workspace_changes_with_patch(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    (repo / "tracked.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )

    def fake_executor(context, emit):
        workspace = Path(context.workspace)
        (workspace / "tracked.txt").write_text("one\ntwo\n", encoding="utf-8")
        (workspace / "created.txt").write_text("new\nfile\n", encoding="utf-8")
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))

    response = client.post("/api/web-chat/runs", json={"input": "Change files", "workspace": str(repo)})
    assert response.status_code == 202
    run = response.json()

    with client.stream("GET", f"/api/web-chat/runs/{run['runId']}/events") as stream:
        body = stream.read().decode()

    assert "event: message.completed" in body
    assert '"changes"' in body
    assert "created.txt" in body

    detail = client.get(f"/api/web-chat/sessions/{run['sessionId']}?includeWorkspaceChanges=true")

    assert detail.status_code == 200
    assistant_parts = detail.json()["messages"][1]["parts"]
    assert [part["type"] for part in assistant_parts] == ["text", "changes"]
    changes = assistant_parts[1]["changes"]
    assert changes["workspace"] == str(repo)
    assert changes["runId"] == run["runId"]
    assert changes["files"] == [
        {"path": "created.txt", "status": "created", "additions": 2, "deletions": 0},
        {"path": "tracked.txt", "status": "edited", "additions": 1, "deletions": 0},
    ]
    assert changes["totalFiles"] == 2
    assert changes["totalAdditions"] == 3
    assert changes["totalDeletions"] == 0
    assert changes["patchTruncated"] is False
    patch_by_path = {file["path"]: file["patch"] for file in changes["patch"]["files"]}
    assert "+two" in patch_by_path["tracked.txt"]
    assert "+new" in patch_by_path["created.txt"]


def test_runs_use_isolated_worktrees_per_chat(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    monkeypatch.setenv("HERMES_WEB_CHAT_WORKTREE_ROOT", str(tmp_path / "worktrees"))
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    seen_workspaces = []

    def fake_executor(context, emit):
        workspace = Path(context.workspace)
        seen_workspaces.append(workspace)
        assert context.source_workspace == str(repo)
        assert workspace != repo
        (workspace / "tracked.txt").write_text(f"base\n{context.session_id}\n", encoding="utf-8")
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))
    first = client.post("/api/web-chat/runs", json={"input": "First", "workspace": str(repo)})
    second = client.post("/api/web-chat/runs", json={"input": "Second", "workspace": str(repo)})
    assert first.status_code == 202
    assert second.status_code == 202
    with client.stream("GET", f"/api/web-chat/runs/{first.json()['runId']}/events") as stream:
        stream.read()
    with client.stream("GET", f"/api/web-chat/runs/{second.json()['runId']}/events") as stream:
        stream.read()

    assert len(seen_workspaces) == 2
    assert seen_workspaces[0] != seen_workspaces[1]
    assert seen_workspaces[0].is_dir()
    assert seen_workspaces[1].is_dir()
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "base\n"

    first_detail = client.get(f"/api/web-chat/sessions/{first.json()['sessionId']}?includeWorkspaceChanges=true").json()
    second_detail = client.get(f"/api/web-chat/sessions/{second.json()['sessionId']}?includeWorkspaceChanges=true").json()
    first_changes = first_detail["messages"][1]["parts"][1]["changes"]
    second_changes = second_detail["messages"][1]["parts"][1]["changes"]
    assert first_changes["workspace"] == str(repo)
    assert second_changes["workspace"] == str(repo)
    assert first.json()["sessionId"] in first_changes["patch"]["files"][0]["patch"]
    assert second.json()["sessionId"] in second_changes["patch"]["files"][0]["patch"]
    assert first_detail["isolatedWorkspace"]["worktreePath"] == str(seen_workspaces[0])


def test_isolated_worktree_defaults_to_project_hermes_dir(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    monkeypatch.delenv("HERMES_WEB_CHAT_WORKTREE_ROOT", raising=False)
    repo = git_repo(tmp_path)
    (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    seen = {}

    def fake_executor(context, emit):
        workspace = Path(context.workspace)
        seen["workspace"] = workspace
        (workspace / "tracked.txt").write_text("base\nproject-local\n", encoding="utf-8")
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))
    start = client.post("/api/web-chat/runs", json={"input": "Change", "workspace": str(repo)}).json()
    with client.stream("GET", f"/api/web-chat/runs/{start['runId']}/events") as stream:
        stream.read()

    expected_root = repo / ".hermes" / "web-chat" / "worktrees"
    assert seen["workspace"].is_relative_to(expected_root)
    source_status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain=v1"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert source_status.stdout == ""



def test_delete_session_removes_isolated_worktree(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    monkeypatch.setenv("HERMES_WEB_CHAT_WORKTREE_ROOT", str(tmp_path / "worktrees"))
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    seen = {}

    def fake_executor(context, emit):
        workspace = Path(context.workspace)
        seen["workspace"] = workspace
        (workspace / "tracked.txt").write_text("base\ndirty\n", encoding="utf-8")
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))
    start = client.post("/api/web-chat/runs", json={"input": "Change", "workspace": str(repo)}).json()
    with client.stream("GET", f"/api/web-chat/runs/{start['runId']}/events") as stream:
        stream.read()
    assert seen["workspace"].is_dir()

    response = client.delete(f"/api/web-chat/sessions/{start['sessionId']}")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert not seen["workspace"].exists()


def test_start_run_reports_later_edits_when_git_status_is_already_dirty(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    (repo / "tracked.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )

    def first_executor(context, emit):
        workspace = Path(context.workspace)
        (workspace / "tracked.txt").write_text("one\ntwo\n", encoding="utf-8")
        return "First done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(first_executor))
    first = client.post("/api/web-chat/runs", json={"input": "Change file", "workspace": str(repo)})
    assert first.status_code == 202
    with client.stream("GET", f"/api/web-chat/runs/{first.json()['runId']}/events") as stream:
        stream.read()

    def second_executor(context, emit):
        workspace = Path(context.workspace)
        (workspace / "tracked.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
        return "Second done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(second_executor))
    second = client.post(
        "/api/web-chat/runs",
        json={"input": "Change it again", "workspace": str(repo), "sessionId": first.json()["sessionId"]},
    )
    assert second.status_code == 202
    with client.stream("GET", f"/api/web-chat/runs/{second.json()['runId']}/events") as stream:
        body = stream.read().decode()

    assert "event: message.completed" in body
    assert '"changes"' in body
    assert "tracked.txt" in body
    assert "+three" in body

    detail = client.get(f"/api/web-chat/sessions/{first.json()['sessionId']}?includeWorkspaceChanges=true")
    messages = detail.json()["messages"]
    assert [part["type"] for part in messages[3]["parts"]] == ["text", "changes"]
    second_changes = messages[3]["parts"][1]["changes"]
    assert second_changes["runId"] == second.json()["runId"]
    assert second_changes["files"] == [
        {"path": "tracked.txt", "status": "edited", "additions": 2, "deletions": 0},
    ]
    assert "+three" in second_changes["patch"]["files"][0]["patch"]


def test_start_run_is_idempotent_for_retried_client_message_id(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = git_repo(tmp_path)
    release_executor = threading.Event()
    executor_started = threading.Event()
    seen_runs = []

    def blocking_executor(context, emit):
        seen_runs.append(context.run_id)
        executor_started.set()
        assert release_executor.wait(timeout=2)
        emit({"type": "message.delta", "content": "Done"})
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(blocking_executor))

    payload = {"input": "Say done", "workspace": str(repo), "clientMessageId": "client-message-retry"}
    first = client.post("/api/web-chat/runs", json=payload)
    assert first.status_code == 202
    assert executor_started.wait(timeout=2)

    retry = client.post("/api/web-chat/runs", json={**payload, "sessionId": first.json()["sessionId"]})
    assert retry.status_code == 202
    assert retry.json()["sessionId"] == first.json()["sessionId"]
    assert retry.json()["runId"] == first.json()["runId"]
    assert retry.json()["userMessageId"] == first.json()["userMessageId"]
    assert seen_runs == [first.json()["runId"]]

    release_executor.set()
    with client.stream("GET", f"/api/web-chat/runs/{first.json()['runId']}/events") as stream:
        stream.read()

    detail = client.get(f"/api/web-chat/sessions/{first.json()['sessionId']}")
    assert [message["role"] for message in detail.json()["messages"]] == ["user", "assistant"]
    assert detail.json()["messages"][0]["clientMessageId"] == "client-message-retry"


def test_start_run_allows_no_workspace(client, monkeypatch):
    import hermes_cli.web_chat as web_chat

    seen = {}

    def executor(context, emit):
        seen["workspace"] = context.workspace
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(executor))

    response = client.post("/api/web-chat/runs", json={"input": "Say done", "workspace": None})

    assert response.status_code == 202
    assert seen["workspace"] is None


def test_resume_run_keeps_existing_workspace_when_omitted(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat
    from hermes_state import SessionDB

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)

    db = SessionDB()
    db.create_session("existing-session", source="web-chat", model_config={"workspace": str(repo)})
    db.append_message("existing-session", "user", "Existing message")
    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(lambda context, emit: "Done"))

    response = client.post("/api/web-chat/runs", json={"sessionId": "existing-session", "input": "Continue"})

    assert response.status_code == 202
    detail = client.get("/api/web-chat/sessions/existing-session")
    assert detail.status_code == 200
    assert detail.json()["session"]["workspace"] == str(repo)


def test_resume_run_clears_workspace_when_requested(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat
    from hermes_state import SessionDB

    repo = git_repo(tmp_path)

    seen = {}

    def executor(context, emit):
        seen["workspace"] = context.workspace
        return "Done"

    db = SessionDB()
    db.create_session("existing-session", source="web-chat", model_config={"workspace": str(repo)})
    db.append_message("existing-session", "user", "Existing message")
    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(executor))

    response = client.post("/api/web-chat/runs", json={
        "sessionId": "existing-session",
        "input": "Continue without workspace",
        "workspace": None,
    })

    assert response.status_code == 202
    assert seen["workspace"] is None
    detail = client.get("/api/web-chat/sessions/existing-session")
    assert detail.status_code == 200
    assert detail.json()["session"]["workspace"] is None


def test_run_events_accept_session_token_query_for_eventsource(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat
    from hermes_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN

    repo = git_repo(tmp_path)

    def fake_executor(context, emit):
        emit({"type": "message.delta", "content": "Done"})
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))

    start = client.post("/api/web-chat/runs", json={"input": "Say done", "workspace": str(repo)}).json()
    del client.headers[_SESSION_HEADER_NAME]

    with client.stream("GET", f"/api/web-chat/runs/{start['runId']}/events?session_token={_SESSION_TOKEN}") as stream:
        body = stream.read().decode()

    assert "event: message.delta" in body
    assert "event: run.completed" in body


def test_stop_run_marks_active_run_as_stopping(client, monkeypatch, tmp_path):
    import time
    import hermes_cli.web_chat as web_chat

    repo = git_repo(tmp_path)

    def blocking_executor(context, emit):
        while not context.stop_requested.is_set():
            time.sleep(0.01)
        return ""

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(blocking_executor))
    start = client.post("/api/web-chat/runs", json={"input": "Wait", "workspace": str(repo)}).json()

    response = client.post(f"/api/web-chat/runs/{start['runId']}/stop")

    assert response.status_code == 200
    assert response.json() == {"runId": start["runId"], "stopped": True}


def test_session_detail_exposes_active_run_and_pending_prompt(client, monkeypatch):
    import hermes_cli.web_chat as web_chat
    from hermes_cli.web_chat_modules.models import WebChatPrompt

    prompt_requested = threading.Event()

    def fake_executor(context, emit):
        prompt = WebChatPrompt(
            id="prompt-active",
            runId=context.run_id,
            sessionId=context.session_id,
            kind="approval",
            title="Allow command?",
            choices=[{"id": "deny", "label": "Deny"}],
        )
        prompt_requested.set()
        context.request_prompt(prompt, 5)
        return "done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))
    start = client.post("/api/web-chat/runs", json={"input": "Need approval"}).json()
    assert prompt_requested.wait(timeout=2)

    detail = client.get(f"/api/web-chat/sessions/{start['sessionId']}")

    assert detail.status_code == 200
    active_run = detail.json()["activeRun"]
    assert active_run["runId"] == start["runId"]
    assert active_run["sessionId"] == start["sessionId"]
    assert active_run["status"] == "running"
    assert active_run["prompts"][0]["id"] == "prompt-active"
    assert active_run["prompts"][0]["status"] == "pending"

    response = client.post(
        f"/api/web-chat/runs/{start['runId']}/prompts/prompt-active/response",
        json={"choice": "deny"},
    )
    assert response.status_code == 200
    with client.stream("GET", f"/api/web-chat/runs/{start['runId']}/events") as stream:
        stream.read()


def test_run_events_can_be_replayed_from_event_id(client, monkeypatch):
    import hermes_cli.web_chat as web_chat

    def fake_executor(context, emit):
        emit({"type": "message.delta", "content": "Done"})
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))
    start = client.post("/api/web-chat/runs", json={"input": "Say done"}).json()

    with client.stream("GET", f"/api/web-chat/runs/{start['runId']}/events") as stream:
        first_body = stream.read().decode()
    with client.stream("GET", f"/api/web-chat/runs/{start['runId']}/events?after=0") as stream:
        replayed_body = stream.read().decode()

    assert "id: 1" in first_body
    assert "event: run.started" in replayed_body
    assert "event: message.delta" in replayed_body
    assert "event: run.completed" in replayed_body
