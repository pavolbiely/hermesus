"""Tests for native web chat API endpoints."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def client(monkeypatch, tmp_path, _isolate_hermes_home):
    try:
        from starlette.testclient import TestClient
    except ImportError:
        pytest.skip("fastapi/starlette not installed")

    import hermes_state
    from hermes_constants import get_hermes_home
    from hermes_cli.web_server import app, _SESSION_HEADER_NAME, _SESSION_TOKEN

    monkeypatch.setattr(hermes_state, "DEFAULT_DB_PATH", get_hermes_home() / "state.db")
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HERMES_WEB_CHAT_PROJECT_ROOT", str(project_root))

    test_client = TestClient(app)
    test_client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
    return test_client


def _assert_iso_timestamp(value: str):
    assert datetime.fromisoformat(value).tzinfo is not None


def _git_repo(tmp_path, name: str = "repo"):
    repo = tmp_path / name
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    return repo


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
        "reasoningEffort": None,
        "workspace": None,
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
    assert data["session"]["reasoningEffort"] is None
    assert [message["role"] for message in data["messages"]] == ["user", "assistant"]
    assert data["messages"][0]["parts"] == [{"type": "text", "text": "Can you help?", "name": None, "status": None, "input": None, "output": None, "url": None, "mediaType": None, "approvalId": None, "changes": None, "attachments": None}]
    assert data["messages"][1]["parts"][0]["type"] == "reasoning"
    assert data["messages"][1]["parts"][0]["text"] == "Short reasoning"
    assert data["messages"][1]["parts"][1]["text"] == "Yes."


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
            "files": ["/Users/pavolbiely/Sites/hermesum/web/package.json"],
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
        "files": ["/Users/pavolbiely/Sites/hermesum/web/package.json"],
    }


def test_returns_chat_capabilities(client, monkeypatch):
    import hermes_cli.web_chat as web_chat

    monkeypatch.setattr(web_chat, "_available_model_ids", lambda: ["gpt-5.4", "gpt-5.3-codex"])

    response = client.get("/api/web-chat/capabilities")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "codex"
    assert data["defaultModel"] == "gpt-5.4"
    assert data["models"] == [
        {
            "id": "gpt-5.4",
            "label": "gpt-5.4",
            "reasoningEfforts": ["none", "low", "medium", "high", "xhigh"],
            "defaultReasoningEffort": "none",
        },
        {
            "id": "gpt-5.3-codex",
            "label": "gpt-5.3-codex",
            "reasoningEfforts": ["low", "medium", "high", "xhigh"],
            "defaultReasoningEffort": "medium",
        },
    ]


def test_returns_profiles_for_composer(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    active = tmp_path / "profiles" / "main"
    alt = tmp_path / "profiles" / "alt"
    active.mkdir(parents=True)
    alt.mkdir()
    monkeypatch.setattr(web_chat, "_profile_dependencies", lambda: (
        lambda: "main",
        lambda: [SimpleNamespace(name="main", path=active), SimpleNamespace(name="alt", path=alt)],
        lambda name: True,
        lambda name: str(tmp_path / "profiles" / name),
        lambda name: None,
        lambda name: None,
    ))

    response = client.get("/api/web-chat/profiles")

    assert response.status_code == 200
    assert response.json() == {
        "profiles": [
            {"id": "main", "label": "main", "path": str(active), "active": True},
            {"id": "alt", "label": "alt", "path": str(alt), "active": False},
        ],
        "activeProfile": "main",
    }


def test_profiles_endpoint_reports_read_errors(client, monkeypatch):
    import hermes_cli.web_chat as web_chat

    def raise_error():
        raise RuntimeError("profile db unavailable")

    monkeypatch.setattr(web_chat, "_profile_dependencies", raise_error)

    response = client.get("/api/web-chat/profiles")

    assert response.status_code == 500
    assert response.json()["detail"] == "Could not load Hermes profiles: profile db unavailable"


def test_switches_active_profile(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    active = tmp_path / "profiles" / "main"
    alt = tmp_path / "profiles" / "alt"
    active.mkdir(parents=True)
    alt.mkdir()
    selected = {"profile": "main"}

    monkeypatch.setattr(web_chat, "_profile_dependencies", lambda: (
        lambda: selected["profile"],
        lambda: [SimpleNamespace(name="main", path=active), SimpleNamespace(name="alt", path=alt)],
        lambda name: name in {"main", "alt"},
        lambda name: str(tmp_path / "profiles" / name),
        lambda name: selected.update(profile=name),
        lambda name: None,
    ))

    response = client.post("/api/web-chat/profiles/active", json={"profile": "alt", "restart": False})

    assert response.status_code == 200
    assert selected == {"profile": "alt"}
    assert response.json() == {
        "profiles": [
            {"id": "main", "label": "main", "path": str(active), "active": False},
            {"id": "alt", "label": "alt", "path": str(alt), "active": True},
        ],
        "activeProfile": "alt",
        "restarting": False,
    }


def test_switch_profile_rejects_running_chats(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    active = tmp_path / "profiles" / "main"
    alt = tmp_path / "profiles" / "alt"
    active.mkdir(parents=True)
    alt.mkdir()
    monkeypatch.setattr(web_chat, "_profile_dependencies", lambda: (
        lambda: "main",
        lambda: [SimpleNamespace(name="main", path=active), SimpleNamespace(name="alt", path=alt)],
        lambda name: name in {"main", "alt"},
        lambda name: str(tmp_path / "profiles" / name),
        lambda name: None,
        lambda name: None,
    ))
    monkeypatch.setattr(web_chat, "run_manager", SimpleNamespace(has_running_runs=lambda: True))

    response = client.post("/api/web-chat/profiles/active", json={"profile": "alt", "restart": False})

    assert response.status_code == 409
    assert response.json()["detail"] == "Wait for running chats to finish before switching profiles."


def test_manages_workspaces_for_composer(client, tmp_path):
    hermesum = tmp_path / "hermesum"
    book = tmp_path / "book"
    hermesum.mkdir()
    book.mkdir()

    create = client.post("/api/web-chat/workspaces", json={"label": "Hermesum", "path": str(hermesum)})

    assert create.status_code == 201
    created = create.json()
    assert created["workspace"]["label"] == "Hermesum"
    assert created["workspace"]["path"] == str(hermesum.resolve())
    assert created["workspace"]["active"] is False

    workspace_id = created["workspace"]["id"]
    update = client.patch(
        f"/api/web-chat/workspaces/{workspace_id}",
        json={"label": "Book", "path": str(book)},
    )

    assert update.status_code == 200
    assert update.json()["workspace"] == {
        "id": workspace_id,
        "label": "Book",
        "path": str(book.resolve()),
        "active": False,
    }

    list_response = client.get("/api/web-chat/workspaces")
    assert list_response.status_code == 200
    assert list_response.json() == {
        "workspaces": [update.json()["workspace"]],
        "activeWorkspace": None,
    }

    delete = client.delete(f"/api/web-chat/workspaces/{workspace_id}")
    assert delete.status_code == 200
    assert delete.json() == {"ok": True}
    assert client.get("/api/web-chat/workspaces").json() == {"workspaces": [], "activeWorkspace": None}


def test_managed_workspaces_are_stored_in_project_hermes_settings(client, tmp_path, monkeypatch):
    project = tmp_path / "settings-project"
    workspace = tmp_path / "workspace"
    project.mkdir()
    workspace.mkdir()
    monkeypatch.setenv("HERMES_WEB_CHAT_PROJECT_ROOT", str(project))

    response = client.post("/api/web-chat/workspaces", json={"label": "Workspace", "path": str(workspace)})

    assert response.status_code == 201
    workspace_id = response.json()["workspace"]["id"]
    settings_path = project / ".hermes" / "web-chat" / "settings.json"
    assert settings_path.exists()
    assert json.loads(settings_path.read_text(encoding="utf-8")) == {
        "version": 1,
        "workspaces": [
            {
                "id": workspace_id,
                "label": "Workspace",
                "path": str(workspace.resolve()),
            }
        ],
    }

    list_response = client.get("/api/web-chat/workspaces")
    assert list_response.status_code == 200
    assert list_response.json()["workspaces"] == [
        {
            "id": workspace_id,
            "label": "Workspace",
            "path": str(workspace.resolve()),
            "active": False,
        }
    ]


def test_migrates_legacy_session_db_workspaces_to_project_settings(client, tmp_path, monkeypatch):
    from hermes_state import SessionDB
    from hermes_cli import web_chat

    project = tmp_path / "migration-project"
    workspace = tmp_path / "legacy-workspace"
    project.mkdir()
    workspace.mkdir()
    monkeypatch.setenv("HERMES_WEB_CHAT_PROJECT_ROOT", str(project))

    db = SessionDB()
    web_chat._ensure_workspace_schema(db)
    db._execute_write(
        lambda conn: conn.execute(
            """
            INSERT INTO web_chat_workspaces (id, label, path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("legacy-id", "Legacy", str(workspace.resolve()), 1.0, 1.0),
        )
    )

    response = client.get("/api/web-chat/workspaces")

    assert response.status_code == 200
    assert response.json()["workspaces"] == [
        {
            "id": "legacy-id",
            "label": "Legacy",
            "path": str(workspace.resolve()),
            "active": False,
        }
    ]
    settings_path = project / ".hermes" / "web-chat" / "settings.json"
    assert json.loads(settings_path.read_text(encoding="utf-8")) == {
        "version": 1,
        "workspaces": [
            {
                "id": "legacy-id",
                "label": "Legacy",
                "path": str(workspace.resolve()),
            }
        ],
    }


def test_suggests_workspace_directories(client, tmp_path):
    (tmp_path / "hermesum").mkdir()
    (tmp_path / "book").mkdir()
    (tmp_path / "hermesum.txt").write_text("not a directory", encoding="utf-8")

    response = client.get("/api/web-chat/workspace-directories", params={"prefix": str(tmp_path / "her")})

    assert response.status_code == 200
    suggestions = response.json()["suggestions"]
    assert str((tmp_path / "hermesum").resolve()) in suggestions
    assert all(Path(suggestion).is_dir() for suggestion in suggestions)
    assert not any(suggestion.endswith("hermesum.txt") for suggestion in suggestions)


def test_create_workspace_rejects_missing_directory(client, tmp_path):
    response = client.post("/api/web-chat/workspaces", json={
        "label": "Missing",
        "path": str(tmp_path / "missing"),
    })

    assert response.status_code == 400
    assert response.json()["detail"] == "Directory does not exist"


def test_returns_workspace_change_summary(client, tmp_path, monkeypatch):
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
    (repo / "tracked.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (repo / "new.txt").write_text("new\nfile\n", encoding="utf-8")
    monkeypatch.chdir(repo)

    response = client.get("/api/web-chat/workspace-changes")

    assert response.status_code == 200
    assert response.json() == {
        "files": [
            {"path": "tracked.txt", "status": "edited", "additions": 2, "deletions": 0},
            {"path": "new.txt", "status": "created", "additions": 2, "deletions": 0},
        ],
        "totalFiles": 2,
        "totalAdditions": 4,
        "totalDeletions": 0,
    }


def test_session_detail_does_not_attach_live_workspace_changes(client, tmp_path, monkeypatch):
    import hermes_cli.web_chat as web_chat
    from hermes_state import SessionDB

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
    (repo / "tracked.txt").write_text("one\ntwo\n", encoding="utf-8")
    monkeypatch.chdir(repo)

    db = SessionDB()
    db.create_session("session-without-persisted-changes", source="web-chat", model="test-model")
    db.append_message("session-without-persisted-changes", "user", "Change a file")
    db.append_message("session-without-persisted-changes", "assistant", "Done")

    def fail_live_workspace_changes(_workspace):
        raise AssertionError("session detail must not compute live workspace changes")

    monkeypatch.setattr(web_chat, "_workspace_changes", fail_live_workspace_changes)

    response = client.get("/api/web-chat/sessions/session-without-persisted-changes?includeWorkspaceChanges=true")

    assert response.status_code == 200
    assert [part["type"] for part in response.json()["messages"][1]["parts"]] == ["text"]


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
    })
    assert response.status_code == 202
    data = response.json()
    assert data["sessionId"]
    assert data["runId"]
    assert seen == {"model": "gpt-5.3-codex", "reasoningEffort": "high", "workspace": str(repo)}

    with client.stream("GET", f"/api/web-chat/runs/{data['runId']}/events") as stream:
        body = stream.read().decode()

    assert "event: run.started" in body
    assert "event: message.delta" in body
    assert "event: message.completed" in body
    assert "event: run.completed" in body

    detail = client.get(f"/api/web-chat/sessions/{data['sessionId']}")
    assert [message["role"] for message in detail.json()["messages"]] == ["user", "assistant"]
    assert detail.json()["messages"][1]["parts"][0]["text"] == "Done"
    assert detail.json()["session"]["model"] == "gpt-5.3-codex"
    assert detail.json()["session"]["reasoningEffort"] == "high"
    assert detail.json()["session"]["workspace"] == str(repo)


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
        (repo / "tracked.txt").write_text("one\ntwo\n", encoding="utf-8")
        (repo / "created.txt").write_text("new\nfile\n", encoding="utf-8")
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))

    response = client.post("/api/web-chat/runs", json={"input": "Change files", "workspace": str(repo)})
    assert response.status_code == 202
    run = response.json()

    with client.stream("GET", f"/api/web-chat/runs/{run['runId']}/events") as stream:
        stream.read()

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

    repo = _git_repo(tmp_path)

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


def test_start_run_rejects_missing_workspace(client, tmp_path):
    response = client.post("/api/web-chat/runs", json={
        "input": "Use missing workspace",
        "workspace": str(tmp_path / "missing"),
    })

    assert response.status_code == 400
    assert response.json()["detail"] == "Directory does not exist"


def test_start_run_rejects_unmanaged_non_git_workspace(client, tmp_path):
    directory = tmp_path / "plain-directory"
    directory.mkdir()

    response = client.post("/api/web-chat/runs", json={
        "input": "Use plain directory",
        "workspace": str(directory),
    })

    assert response.status_code == 400
    assert response.json()["detail"] == "Directory is not a managed or git workspace"


def test_workspace_changes_uses_requested_workspace(client, tmp_path, monkeypatch):
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    for repo in (repo_a, repo_b):
        repo.mkdir()
        subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
        (repo / "tracked.txt").write_text("one\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "initial"],
            check=True,
            capture_output=True,
        )
    (repo_b / "tracked.txt").write_text("one\ntwo\n", encoding="utf-8")
    monkeypatch.chdir(repo_a)

    response = client.get("/api/web-chat/workspace-changes", params={"workspace": str(repo_b)})

    assert response.status_code == 200
    assert response.json()["files"] == [{"path": "tracked.txt", "status": "edited", "additions": 1, "deletions": 0}]


def test_start_run_rejects_missing_profile(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = _git_repo(tmp_path)
    monkeypatch.setattr(web_chat, "_profile_dependencies", lambda: (
        lambda: "main",
        lambda: [],
        lambda name: False,
        lambda name: str(tmp_path / "profiles" / name),
        lambda name: None,
        lambda name: None,
    ))

    response = client.post("/api/web-chat/runs", json={"input": "Hi", "workspace": str(repo), "profile": "missing"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Hermes profile does not exist"


def test_start_run_rejects_unsafe_profile_switch_with_clear_message(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = _git_repo(tmp_path)
    monkeypatch.setattr(web_chat, "_profile_dependencies", lambda: (
        lambda: "main",
        lambda: [],
        lambda name: True,
        lambda name: str(tmp_path / "profiles" / name),
        lambda name: None,
        lambda name: None,
    ))

    response = client.post("/api/web-chat/runs", json={"input": "Hi", "workspace": str(repo), "profile": "alt"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Switching Hermes profile requires a backend restart in this prototype. Current profile: main."


def test_start_run_accepts_current_profile(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = _git_repo(tmp_path)
    seen = {}
    monkeypatch.setattr(web_chat, "_profile_dependencies", lambda: (
        lambda: "main",
        lambda: [],
        lambda name: True,
        lambda name: str(tmp_path / "profiles" / name),
        lambda name: None,
        lambda name: None,
    ))

    def fake_executor(context, emit):
        seen["profile"] = context.profile
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))

    response = client.post("/api/web-chat/runs", json={"input": "Hi", "workspace": str(repo), "profile": "main"})

    assert response.status_code == 202
    assert seen == {"profile": "main"}


def test_upload_attachment_stores_file_in_project_attachments(client, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)

    response = client.post(
        "/api/web-chat/attachments",
        data={"workspace": str(repo)},
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )

    assert response.status_code == 201
    attachment = response.json()["attachments"][0]
    assert attachment["id"]
    assert attachment["name"] == "notes.txt"
    assert attachment["mediaType"] == "text/plain"
    assert attachment["size"] == 5
    assert attachment["workspace"] == str(repo)
    assert attachment["relativePath"] == ".hermes/attachments/notes.txt"
    assert attachment["url"] == f"/api/web-chat/attachments/{attachment['id']}/content"
    assert attachment["exists"] is True
    assert attachment["path"] == str(repo / ".hermes" / "attachments" / "notes.txt")
    assert (repo / ".hermes" / "attachments" / "notes.txt").read_bytes() == b"hello"


def test_upload_attachment_uses_unique_filename_when_file_exists(client, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)

    first = client.post(
        "/api/web-chat/attachments",
        data={"workspace": str(repo)},
        files=[("files", ("image.png", b"first", "image/png"))],
    )
    second = client.post(
        "/api/web-chat/attachments",
        data={"workspace": str(repo)},
        files=[("files", ("image.png", b"second", "image/png"))],
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["attachments"][0]["relativePath"] == ".hermes/attachments/image.png"
    assert second.json()["attachments"][0]["relativePath"] == ".hermes/attachments/image 2.png"
    assert (repo / ".hermes" / "attachments" / "image.png").read_bytes() == b"first"
    assert (repo / ".hermes" / "attachments" / "image 2.png").read_bytes() == b"second"


def test_attachment_metadata_and_content_endpoints(client, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)

    upload = client.post(
        "/api/web-chat/attachments",
        data={"workspace": str(repo)},
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )
    attachment_id = upload.json()["attachments"][0]["id"]

    metadata = client.get(f"/api/web-chat/attachments/{attachment_id}")
    content = client.get(f"/api/web-chat/attachments/{attachment_id}/content")

    assert metadata.status_code == 200
    assert metadata.json()["exists"] is True
    assert metadata.json()["url"] == f"/api/web-chat/attachments/{attachment_id}/content"
    assert content.status_code == 200
    assert content.content == b"hello"
    assert content.headers["content-type"].startswith("text/plain")


def test_attachment_content_can_be_loaded_by_workspace_after_registry_reset(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)

    upload = client.post(
        "/api/web-chat/attachments",
        data={"workspace": str(repo)},
        files=[("files", ("baner.jpg", b"image", "image/jpeg"))],
    )
    attachment_id = upload.json()["attachments"][0]["id"]

    web_chat._KNOWN_ATTACHMENT_ROOTS.clear()
    monkeypatch.setattr(
        web_chat,
        "_list_web_chat_workspaces",
        lambda: web_chat.WebChatWorkspacesResponse(workspaces=[], activeWorkspace=None),
    )

    missing_without_workspace = client.get(f"/api/web-chat/attachments/{attachment_id}/content")
    content = client.get(
        f"/api/web-chat/attachments/{attachment_id}/content",
        params={"workspace": str(repo)},
    )

    assert missing_without_workspace.status_code == 404
    assert content.status_code == 200
    assert content.content == b"image"
    assert content.headers["content-type"].startswith("image/jpeg")


def test_attachment_metadata_survives_deleted_file(client, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)

    upload = client.post(
        "/api/web-chat/attachments",
        data={"workspace": str(repo)},
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )
    attachment = upload.json()["attachments"][0]
    (repo / ".hermes" / "attachments" / "notes.txt").unlink()

    metadata = client.get(f"/api/web-chat/attachments/{attachment['id']}")
    content = client.get(f"/api/web-chat/attachments/{attachment['id']}/content")

    assert metadata.status_code == 200
    assert metadata.json()["exists"] is False
    assert content.status_code == 404


def test_delete_session_does_not_delete_attachment_files(client, monkeypatch, tmp_path):
    from pathlib import Path
    import hermes_cli.web_chat as web_chat

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    upload = client.post(
        "/api/web-chat/attachments",
        data={"workspace": str(repo)},
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )
    attachment = upload.json()["attachments"][0]

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(lambda context, emit: "Done"))
    run = client.post(
        "/api/web-chat/runs",
        json={"input": "Use this", "workspace": str(repo), "attachments": [attachment["id"]]},
    )
    session_id = run.json()["sessionId"]

    response = client.delete(f"/api/web-chat/sessions/{session_id}")

    assert response.status_code == 200
    assert Path(attachment["path"]).read_bytes() == b"hello"


def test_upload_attachment_requires_workspace(client):
    response = client.post(
        "/api/web-chat/attachments",
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Select a workspace before attaching files."


def test_upload_attachment_rejects_empty_file(client, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)

    response = client.post(
        "/api/web-chat/attachments",
        data={"workspace": str(repo)},
        files=[("files", ("empty.txt", b"", "text/plain"))],
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Attachment is empty"


def test_upload_attachment_rejects_too_large_file(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)

    monkeypatch.setattr(web_chat, "MAX_ATTACHMENT_BYTES", 4)

    response = client.post(
        "/api/web-chat/attachments",
        data={"workspace": str(repo)},
        files=[("files", ("large.txt", b"hello", "text/plain"))],
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "File is too large. Maximum size is 25 MB."


def test_start_run_passes_attachment_context_to_executor(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    upload = client.post(
        "/api/web-chat/attachments",
        data={"workspace": str(repo)},
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )
    attachment_id = upload.json()["attachments"][0]["id"]
    seen = {}

    def fake_executor(context, emit):
        seen["input"] = context.input
        seen["attachments"] = context.attachments
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))

    response = client.post("/api/web-chat/runs", json={"input": "Summarize", "workspace": str(repo), "attachments": [attachment_id]})

    assert response.status_code == 202
    assert "Attached files:" in seen["input"]
    assert "notes.txt" in seen["input"]
    assert str(repo / ".hermes" / "attachments" / "notes.txt") in seen["input"]
    assert seen["attachments"] == [attachment_id]

    detail = client.get(f"/api/web-chat/sessions/{response.json()['sessionId']}")
    user_parts = detail.json()["messages"][0]["parts"]
    assert user_parts[0]["type"] == "media"
    assert user_parts[0]["attachments"][0]["id"] == attachment_id
    assert user_parts[1]["type"] == "text"


def test_start_run_assigns_selected_workspace_to_new_session(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)

    seen = {}

    def fake_executor(context, emit):
        seen["workspace"] = context.workspace
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))

    response = client.post("/api/web-chat/runs", json={"input": "Use workspace", "workspace": str(repo)})

    assert response.status_code == 202
    assert seen["workspace"] == str(repo)

    detail = client.get(f"/api/web-chat/sessions/{response.json()['sessionId']}")
    assert detail.status_code == 200
    assert detail.json()["session"]["workspace"] == str(repo)


def test_start_run_existing_session_inherits_workspace_for_attachments(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat
    from hermes_state import SessionDB

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)

    db = SessionDB()
    db.create_session("session-existing", source="web-chat", model_config={"workspace": str(repo)})
    db.append_message("session-existing", "user", "Existing")

    upload = client.post(
        "/api/web-chat/attachments",
        data={"workspace": str(repo)},
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )
    attachment_id = upload.json()["attachments"][0]["id"]
    seen = {}

    def fake_executor(context, emit):
        seen["workspace"] = context.workspace
        seen["input"] = context.input
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))

    response = client.post(
        "/api/web-chat/runs",
        json={"sessionId": "session-existing", "input": "Use uploaded file", "attachments": [attachment_id]},
    )

    assert response.status_code == 202
    assert seen["workspace"] == str(repo)
    assert str(repo / ".hermes" / "attachments" / "notes.txt") in seen["input"]

    detail = client.get("/api/web-chat/sessions/session-existing")
    assert detail.json()["session"]["workspace"] == str(repo)
    assert detail.json()["messages"][-2]["parts"][0]["attachments"][0]["id"] == attachment_id


def test_start_run_rejects_deleted_attachment_file(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    upload = client.post(
        "/api/web-chat/attachments",
        data={"workspace": str(repo)},
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )
    attachment = upload.json()["attachments"][0]
    (repo / ".hermes" / "attachments" / "notes.txt").unlink()

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(lambda context, emit: "Done"))
    response = client.post("/api/web-chat/runs", json={"input": "Summarize", "workspace": str(repo), "attachments": [attachment["id"]]})

    assert response.status_code == 400
    assert response.json()["detail"] == "Attachment file no longer exists. Upload it again."


def test_start_run_rejects_unknown_attachment(client, tmp_path):
    repo = _git_repo(tmp_path)

    response = client.post("/api/web-chat/runs", json={"input": "Summarize", "workspace": str(repo), "attachments": ["missing"]})

    assert response.status_code == 400
    assert response.json()["detail"] == "Attachment no longer exists. Upload it again."


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


def test_start_run_from_edited_message_does_not_append_duplicate_user_message(client, monkeypatch):
    import hermes_cli.web_chat as web_chat
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("session-edit", source="web-chat")
    message_id = db.append_message("session-edit", "user", "Edited prompt")
    seen = {}

    def fake_executor(context, emit):
        seen["input"] = context.input
        return "New answer"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))

    response = client.post(
        "/api/web-chat/runs",
        json={"sessionId": "session-edit", "input": "Edited prompt", "editedMessageId": str(message_id)},
    )

    assert response.status_code == 202
    assert seen["input"] == "Edited prompt"

    detail = client.get("/api/web-chat/sessions/session-edit")
    messages = detail.json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["id"] == str(message_id)
    assert messages[0]["parts"][0]["text"] == "Edited prompt"
    assert messages[1]["parts"][0]["text"] == "New answer"


def test_start_run_from_edited_message_requires_last_user_message(client):
    from hermes_state import SessionDB

    db = SessionDB()
    db.create_session("session-edit", source="web-chat")
    message_id = db.append_message("session-edit", "user", "Prompt")
    db.append_message("session-edit", "assistant", "Answer")

    response = client.post(
        "/api/web-chat/runs",
        json={"sessionId": "session-edit", "input": "Prompt", "editedMessageId": str(message_id)},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Edited message must be the latest message in the chat."


def test_start_run_allows_duplicate_initial_titles(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = _git_repo(tmp_path)

    def fake_executor(context, emit):
        return "Done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))

    first = client.post("/api/web-chat/runs", json={"input": "Repeatable title", "workspace": str(repo)})
    second = client.post("/api/web-chat/runs", json={"input": "Repeatable title", "workspace": str(repo)})

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["sessionId"] != second.json()["sessionId"]


def test_start_run_for_existing_session_updates_saved_model_and_reasoning(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat
    from hermes_state import SessionDB

    repo = _git_repo(tmp_path)
    db = SessionDB()
    db.create_session("session-existing", source="web-chat", model="gpt-5.4", model_config={"workspace": str(repo)})
    db.append_message("session-existing", "user", "Existing")

    def fake_executor(context, emit):
        return "Updated"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))

    response = client.post("/api/web-chat/runs", json={
        "sessionId": "session-existing",
        "input": "Switch models",
        "model": "gpt-5.3-codex",
        "reasoningEffort": "xhigh",
    })

    assert response.status_code == 202

    detail = client.get("/api/web-chat/sessions/session-existing")
    assert detail.status_code == 200
    assert detail.json()["session"]["model"] == "gpt-5.3-codex"
    assert detail.json()["session"]["reasoningEffort"] == "xhigh"


def test_invalid_reasoning_effort_falls_back_safely(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = _git_repo(tmp_path)
    seen = {}

    def fake_executor(context, emit):
        seen["model"] = context.model
        seen["reasoningEffort"] = context.reasoning_effort
        return "Done"

    monkeypatch.setattr(web_chat, "_available_model_ids", lambda: ["gpt-5.4"])
    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))

    response = client.post("/api/web-chat/runs", json={
        "input": "Use safe defaults",
        "workspace": str(repo),
        "model": "gpt-5.4",
        "reasoningEffort": "banana",
    })

    assert response.status_code == 202
    assert seen == {"model": "gpt-5.4", "reasoningEffort": "none"}


def test_run_events_accept_session_token_query_for_eventsource(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat
    from hermes_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN

    repo = _git_repo(tmp_path)

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

    repo = _git_repo(tmp_path)

    def blocking_executor(context, emit):
        while not context.stop_requested.is_set():
            time.sleep(0.01)
        return ""

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(blocking_executor))
    start = client.post("/api/web-chat/runs", json={"input": "Wait", "workspace": str(repo)}).json()

    response = client.post(f"/api/web-chat/runs/{start['runId']}/stop")

    assert response.status_code == 200
    assert response.json() == {"runId": start["runId"], "stopped": True}
