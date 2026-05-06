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
        "commits": [],
        "hasMoreCommits": False,
        "compareUrl": None,
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
        lambda: update_status_response(
            updateAvailable=True,
            remoteRevision="def67890",
            hasMoreCommits=True,
            compareUrl="https://github.com/NousResearch/hermes-agent/compare/abc12345...def67890",
            commits=[
                {
                    "hash": "def678901234",
                    "shortHash": "def67890",
                    "subject": "Improve update flow",
                    "author": "Test",
                    "committedAt": "2026-01-01T00:00:00+00:00",
                    "url": "https://github.com/NousResearch/hermes-agent/commit/def678901234",
                }
            ],
        ),
    )

    response = client.get("/api/web-chat/update")

    assert response.status_code == 200
    assert response.json()["updateAvailable"] is True
    assert response.json()["runtimeOutOfSync"] is False
    assert response.json()["remoteRevision"] == "def67890"
    assert response.json()["commits"][0]["subject"] == "Improve update flow"
    assert response.json()["commits"][0]["url"] == "https://github.com/NousResearch/hermes-agent/commit/def678901234"
    assert response.json()["hasMoreCommits"] is True
    assert response.json()["compareUrl"] == "https://github.com/NousResearch/hermes-agent/compare/abc12345...def67890"


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


def test_update_commits_returns_latest_remote_commits(tmp_path):
    from hermes_cli.web_chat_modules.updates import _update_commits

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    current_head = _commit(repo, "initial")
    newest_head = None
    for index in range(12):
        newest_head = _commit(repo, f"remote ahead {index}")

    commits = _update_commits(repo, current_head, newest_head)

    assert len(commits) == 11
    assert commits[0].subject == "remote ahead 11"
    assert commits[-1].subject == "remote ahead 1"


def test_github_compare_url_supports_https_and_ssh_remotes():
    from hermes_cli.web_chat_modules.updates import _github_compare_url

    assert _github_compare_url(
        "https://github.com/NousResearch/hermes-agent.git",
        "abc123",
        "def456",
    ) == "https://github.com/NousResearch/hermes-agent/compare/abc123...def456"
    assert _github_compare_url(
        "git@github.com:NousResearch/hermes-agent.git",
        "abc123",
        "def456",
    ) == "https://github.com/NousResearch/hermes-agent/compare/abc123...def456"


def test_update_commits_includes_github_commit_urls(tmp_path):
    from hermes_cli.web_chat_modules.updates import _update_commits

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    current_head = _commit(repo, "initial")
    remote_head = _commit(repo, "remote ahead")

    commits = _update_commits(
        repo,
        current_head,
        remote_head,
        remote_url="https://github.com/NousResearch/hermes-agent.git",
    )

    assert commits[0].url == f"https://github.com/NousResearch/hermes-agent/commit/{remote_head}"
