"""Tests for web chat run lifecycle endpoints."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from web_chat_test_helpers import committed_git_repo, git_repo


def test_start_run_returns_ids_and_persists_messages(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = git_repo(tmp_path)
    seen = {}

    def fake_executor(context, emit):
        seen["model"] = context.model
        seen["reasoningEffort"] = context.reasoning_effort
        seen["workspace"] = context.workspace
        context.usage_metrics = {"tokenCount": 42, "inputTokens": 30, "outputTokens": 12, "contextTokens": 28, "apiCalls": 1}
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
    assert '"tokenCount":42' in body
    assert '"contextTokens":28' in body
    assert '"generationDurationMs"' in body
    assert "event: run.completed" in body

    detail = client.get(f"/api/web-chat/sessions/{data['sessionId']}")
    assert [message["role"] for message in detail.json()["messages"]] == ["user", "assistant"]
    assert detail.json()["messages"][0]["id"] == data["userMessageId"]
    assert detail.json()["messages"][0]["clientMessageId"] == "client-message-1"
    assert detail.json()["messages"][1]["parts"][0]["text"] == "Done"
    assert detail.json()["messages"][0]["tokenCount"] == 30
    assert detail.json()["messages"][0]["inputTokens"] == 30
    assert detail.json()["messages"][1]["tokenCount"] == 42
    assert detail.json()["messages"][1]["outputTokens"] == 12
    assert detail.json()["messages"][1]["contextTokens"] == 28
    assert detail.json()["messages"][1]["apiCalls"] == 1
    assert isinstance(detail.json()["messages"][1]["generationDurationMs"], int)
    assert isinstance(detail.json()["messages"][1]["modelDurationMs"], int)
    assert detail.json()["session"]["model"] == "gpt-5.3-codex"
    assert detail.json()["session"]["reasoningEffort"] == "high"
    assert detail.json()["session"]["workspace"] == str(repo)


def test_run_events_unknown_run_returns_404_before_streaming(client):
    response = client.get("/api/web-chat/runs/missing-run/events")

    assert response.status_code == 404
    assert response.json()["detail"] == "Run not found"


def test_start_run_streams_agent_warning_as_system_event(client, monkeypatch, tmp_path):
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
    assert [message["role"] for message in messages] == ["user", "system", "assistant"]
    assert messages[1]["parts"][0]["type"] == "event"
    assert messages[1]["parts"][0]["eventType"] == "agent_warning"
    assert messages[1]["parts"][0]["description"] == "test warning"
    assert messages[2]["parts"][0]["text"] == "Done"


def test_start_run_streams_and_persists_task_plan(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = git_repo(tmp_path)
    task_plan = {
        "todos": [
            {"id": "1", "content": "Inspect current UI", "status": "completed"},
            {"id": "2", "content": "Build plan card", "status": "in_progress"},
            {"id": "3", "content": "Verify behavior", "status": "pending"},
        ]
    }

    def fake_executor(context, emit):
        emit({
            "type": "task_plan.updated",
            "taskPlan": {
                "items": task_plan["todos"],
                "updatedAt": "2026-04-30T00:00:00+00:00",
            },
        })
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))

    response = client.post("/api/web-chat/runs", json={"input": "Say done", "workspace": str(repo)})
    assert response.status_code == 202
    run = response.json()

    with client.stream("GET", f"/api/web-chat/runs/{run['runId']}/events") as stream:
        body = stream.read().decode()

    assert "event: task_plan.updated" in body
    assert "Build plan card" in body

    detail = client.get(f"/api/web-chat/sessions/{run['sessionId']}")
    assistant = detail.json()["messages"][1]
    task_plan_part = assistant["parts"][0]
    assert task_plan_part["type"] == "task_plan"
    assert task_plan_part["taskPlan"] == {
        "items": task_plan["todos"],
        "updatedAt": "2026-04-30T00:00:00+00:00",
    }
    assert assistant["parts"][1]["text"] == "Done"


def test_task_plan_from_todo_tool_result_normalizes_items():
    from hermes_cli.web_chat_modules.agent_runner import task_plan_from_tool_result

    result = task_plan_from_tool_result(
        "todo",
        json.dumps({
            "todos": [
                {"id": "a", "content": " First task ", "status": "completed"},
                {"content": "Second task", "status": "unknown"},
                {"id": "empty", "content": "   ", "status": "pending"},
            ]
        }),
    )

    assert result is not None
    assert result["items"] == [
        {"id": "a", "content": "First task", "status": "completed"},
        {"id": "item-2", "content": "Second task", "status": "pending"},
    ]
    assert result["updatedAt"]


def test_stop_run_interrupts_executor_and_persists_stopped_event(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = git_repo(tmp_path)
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

    assert "event: message.completed" not in body
    assert "Chat interrupted." not in body
    assert "event: run.stopped" in body
    assert "Should not be persisted" not in body

    detail = client.get(f"/api/web-chat/sessions/{run['sessionId']}")
    messages = detail.json()["messages"]
    assert [message["role"] for message in messages] == ["user", "system"]
    assert messages[1]["parts"][0]["type"] == "event"
    assert messages[1]["parts"][0]["eventType"] == "run_stopped"
    assert messages[1]["parts"][0]["title"] == "Run stopped"
    assert messages[1]["parts"][0]["description"] == "Stopped by user."


def test_start_run_persists_workspace_changes_with_patch(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = committed_git_repo(tmp_path)

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


def test_runs_edit_source_workspace_and_persist_history(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    worktree_root = tmp_path / "worktrees"
    monkeypatch.setenv("HERMES_WEB_CHAT_WORKTREE_ROOT", str(worktree_root))
    repo = committed_git_repo(tmp_path, content="base\n")
    seen = {}

    def fake_executor(context, emit):
        workspace = Path(context.workspace)
        seen["workspace"] = workspace
        seen["source_workspace"] = context.source_workspace
        seen["isolated_workspace"] = context.isolated_workspace
        (workspace / "tracked.txt").write_text("base\nedited in source\n", encoding="utf-8")
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))
    response = client.post("/api/web-chat/runs", json={"input": "Change", "workspace": str(repo)})
    assert response.status_code == 202
    start = response.json()
    with client.stream("GET", f"/api/web-chat/runs/{start['runId']}/events") as stream:
        stream.read()

    assert seen == {
        "workspace": repo,
        "source_workspace": str(repo),
        "isolated_workspace": None,
    }
    assert not worktree_root.exists()
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "base\nedited in source\n"

    detail = client.get(f"/api/web-chat/sessions/{start['sessionId']}?includeWorkspaceChanges=true").json()
    assert detail["isolatedWorkspace"] is None
    changes = detail["messages"][1]["parts"][1]["changes"]
    assert changes["workspace"] == str(repo)
    assert changes["runId"] == start["runId"]
    assert changes["files"] == [
        {"path": "tracked.txt", "status": "edited", "additions": 1, "deletions": 0},
    ]
    assert "+edited in source" in changes["patch"]["files"][0]["patch"]



def test_delete_session_does_not_remove_source_workspace(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    monkeypatch.setenv("HERMES_WEB_CHAT_WORKTREE_ROOT", str(tmp_path / "worktrees"))
    repo = committed_git_repo(tmp_path, content="base\n")
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
    assert seen["workspace"] == repo

    response = client.delete(f"/api/web-chat/sessions/{start['sessionId']}")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert repo.exists()
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "base\ndirty\n"


def test_start_run_reports_later_edits_when_git_status_is_already_dirty(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = committed_git_repo(tmp_path)

    def first_executor(context, emit):
        workspace = Path(context.workspace)
        (workspace / "tracked.txt").write_text("one\ntwo\n", encoding="utf-8")
        (workspace / "other.txt").write_text("other\n", encoding="utf-8")
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
    assert "other.txt" not in body
    assert "+three" in body

    detail = client.get(f"/api/web-chat/sessions/{first.json()['sessionId']}?includeWorkspaceChanges=true")
    messages = detail.json()["messages"]
    assert [part["type"] for part in messages[3]["parts"]] == ["text", "changes"]
    second_changes = messages[3]["parts"][1]["changes"]
    assert second_changes["runId"] == second.json()["runId"]
    assert second_changes["files"] == [
        {"path": "tracked.txt", "status": "edited", "additions": 1, "deletions": 0},
    ]
    assert "+three" in second_changes["patch"]["files"][0]["patch"]
    assert "+two" not in second_changes["patch"]["files"][0]["patch"]


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

    repo = git_repo(tmp_path)

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

    with client.stream("GET", f"/api/web-chat/runs/{start['runId']}/events") as stream:
        body = stream.read().decode()
    assert "event: run.stopped" in body


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

