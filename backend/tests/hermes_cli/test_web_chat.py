"""Tests for native web chat API endpoints."""

from __future__ import annotations

import json

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
    assert response.json()["compressionCount"] == 2


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
