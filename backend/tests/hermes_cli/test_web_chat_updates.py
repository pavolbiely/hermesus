from __future__ import annotations

import subprocess


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def _commit(root, message):
    _git(root, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "--allow-empty", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def update_status_response(**overrides):
    from hermes_cli.web_chat_modules.models import WebChatUpdateStatusResponse

    data = {
        "updateAvailable": False,
        "runtimeOutOfSync": False,
        "upstreamPath": "/tmp/upstream",
        "runtimePath": "/tmp/runtime",
        "branch": "main",
        "currentRevision": "abc12345",
        "remoteRevision": "abc12345",
        "runtimeRevision": "abc12345",
    }
    data.update(overrides)
    return WebChatUpdateStatusResponse(**data)


def app_update_status_response(**overrides):
    from hermes_cli.web_chat_modules.models import WebChatAppUpdateStatusResponse

    data = {
        "updateAvailable": False,
        "appPath": "/tmp/app",
        "branch": "main",
        "currentRevision": "abc12345",
        "remoteRevision": "abc12345",
    }
    data.update(overrides)
    return WebChatAppUpdateStatusResponse(**data)


def test_update_status_endpoint_reports_available_update(client, monkeypatch):
    import hermes_cli.web_chat as web_chat

    monkeypatch.setattr(
        web_chat,
        "_update_status_impl",
        lambda: update_status_response(updateAvailable=True, remoteRevision="def67890"),
    )

    response = client.get("/api/web-chat/update")

    assert response.status_code == 200
    assert response.json()["updateAvailable"] is True
    assert response.json()["runtimeOutOfSync"] is False
    assert response.json()["remoteRevision"] == "def67890"


def test_update_endpoint_runs_update_and_reports_synced_runtime(client, monkeypatch):
    import hermes_cli.web_chat as web_chat

    monkeypatch.setattr(web_chat, "_perform_update_impl", lambda: update_status_response())

    response = client.post("/api/web-chat/update")

    assert response.status_code == 200
    assert response.json()["updateAvailable"] is False
    assert response.json()["runtimeOutOfSync"] is False


def test_app_update_status_endpoint_reports_available_update(client, monkeypatch):
    import hermes_cli.web_chat as web_chat

    monkeypatch.setattr(
        web_chat,
        "_app_update_status_impl",
        lambda: app_update_status_response(updateAvailable=True, remoteRevision="def67890"),
    )

    response = client.get("/api/web-chat/app-update")

    assert response.status_code == 200
    assert response.json()["updateAvailable"] is True
    assert response.json()["appPath"] == "/tmp/app"
    assert response.json()["remoteRevision"] == "def67890"


def test_app_update_endpoint_runs_update(client, monkeypatch):
    import hermes_cli.web_chat as web_chat

    monkeypatch.setattr(web_chat, "_perform_app_update_impl", lambda: app_update_status_response())

    response = client.post("/api/web-chat/app-update")

    assert response.status_code == 200
    assert response.json()["updateAvailable"] is False


def test_has_remote_update_is_false_when_local_is_ahead(tmp_path):
    from hermes_cli.web_chat_modules.updates import _has_remote_update

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    remote_head = _commit(repo, "initial")
    current_head = _commit(repo, "local ahead")

    assert _has_remote_update(repo, current_head, remote_head) is False


def test_has_remote_update_is_true_when_remote_is_ahead(tmp_path):
    from hermes_cli.web_chat_modules.updates import _has_remote_update

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    current_head = _commit(repo, "initial")
    remote_head = _commit(repo, "remote ahead")

    assert _has_remote_update(repo, current_head, remote_head) is True


def test_has_remote_update_is_false_when_revisions_match(tmp_path):
    from hermes_cli.web_chat_modules.updates import _has_remote_update

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    head = _commit(repo, "initial")

    assert _has_remote_update(repo, head, head) is False
