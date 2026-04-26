"""Tests for web chat attachment endpoints and attachment-backed runs."""

from __future__ import annotations

import json
from pathlib import Path

from web_chat_test_helpers import git_repo


def test_upload_attachment_stores_file_in_project_attachments(client, tmp_path):
    repo = git_repo(tmp_path)

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
    repo = git_repo(tmp_path)

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
    repo = git_repo(tmp_path)

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


def test_attachment_content_rejects_tampered_metadata_path(client, tmp_path):
    repo = git_repo(tmp_path)
    secret_path = tmp_path / "secret.txt"
    secret_path.write_text("do not serve", encoding="utf-8")

    upload = client.post(
        "/api/web-chat/attachments",
        data={"workspace": str(repo)},
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )
    attachment = upload.json()["attachments"][0]
    meta_path = repo / ".hermes" / "attachments" / "notes.txt.web-chat.json"
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    metadata["path"] = str(secret_path)
    meta_path.write_text(json.dumps(metadata), encoding="utf-8")

    metadata_response = client.get(f"/api/web-chat/attachments/{attachment['id']}")
    content_response = client.get(f"/api/web-chat/attachments/{attachment['id']}/content")

    assert metadata_response.status_code == 404
    assert content_response.status_code == 404


def test_attachment_content_can_be_loaded_by_workspace_after_registry_reset(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = git_repo(tmp_path)

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
    repo = git_repo(tmp_path)

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
    import hermes_cli.web_chat as web_chat

    repo = git_repo(tmp_path)
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
    repo = git_repo(tmp_path)

    response = client.post(
        "/api/web-chat/attachments",
        data={"workspace": str(repo)},
        files=[("files", ("empty.txt", b"", "text/plain"))],
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Attachment is empty"


def test_upload_attachment_rejects_too_large_file(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat

    repo = git_repo(tmp_path)

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

    repo = git_repo(tmp_path)
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


def test_start_run_existing_session_inherits_workspace_for_attachments(client, monkeypatch, tmp_path):
    import hermes_cli.web_chat as web_chat
    from hermes_state import SessionDB

    repo = git_repo(tmp_path)

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

    repo = git_repo(tmp_path)
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
    repo = git_repo(tmp_path)

    response = client.post("/api/web-chat/runs", json={"input": "Summarize", "workspace": str(repo), "attachments": ["missing"]})

    assert response.status_code == 400
    assert response.json()["detail"] == "Attachment no longer exists. Upload it again."
