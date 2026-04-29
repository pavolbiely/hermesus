"""Tests for web chat profiles, workspaces, and workspace change endpoints."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace


def test_available_model_ids_does_not_use_codex_fallback_for_other_providers(monkeypatch):
    from hermes_cli.web_chat_modules import capabilities

    monkeypatch.setattr(capabilities, "_configured_model_id", lambda: None)
    monkeypatch.setattr(capabilities, "runtime_provider", lambda target_model=None: {"provider": "anthropic"})

    assert capabilities.available_model_ids(resolve_access_token=lambda: "codex-token") == []


def test_returns_chat_capabilities(client, monkeypatch):
    import hermes_cli.web_chat as web_chat
    from hermes_cli.web_chat_modules import capabilities

    monkeypatch.setattr(web_chat, "_active_provider_id", lambda: "test-provider")
    monkeypatch.setattr(capabilities, "active_provider_id", lambda: "test-provider")
    monkeypatch.setattr(web_chat, "_available_model_ids", lambda: ["gpt-5.4", "claude-sonnet-4-6"])
    monkeypatch.setattr(capabilities, "authenticated_model_capabilities", lambda: [])
    monkeypatch.setattr(capabilities, "model_context_window_tokens", lambda model_id: 300000 if model_id == "gpt-5.4" else 200000)
    monkeypatch.setattr(capabilities, "_compression_threshold", lambda: 0.4)

    response = client.get("/api/web-chat/capabilities")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "test-provider"
    assert data["defaultModel"] == "gpt-5.4"
    assert data["defaultProvider"] == "test-provider"
    assert data["models"] == [
        {
            "id": "gpt-5.4",
            "label": "gpt-5.4",
            "reasoningEfforts": ["none", "low", "medium", "high", "xhigh"],
            "defaultReasoningEffort": "none",
            "contextWindowTokens": 300000,
            "autoCompressTokens": 120000,
            "provider": "test-provider",
            "providerLabel": "Test Provider",
        },
        {
            "id": "claude-sonnet-4-6",
            "label": "claude-sonnet-4-6",
            "reasoningEfforts": ["low", "medium", "high"],
            "defaultReasoningEffort": "medium",
            "contextWindowTokens": 200000,
            "autoCompressTokens": 80000,
            "provider": "test-provider",
            "providerLabel": "Test Provider",
        },
    ]


def test_returns_provider_usage(client, monkeypatch):
    import hermes_cli.web_chat as web_chat
    from hermes_cli.web_chat_modules.models import (
        WebChatProviderUsageLimit,
        WebChatProviderUsageResponse,
        WebChatProviderUsageWindow,
    )

    monkeypatch.setattr(
        web_chat,
        "_provider_usage_impl",
        lambda provider=None, model=None: WebChatProviderUsageResponse(
            provider=provider or "openai-codex",
            model=model,
            source="codex",
            available=True,
            limits=[
                WebChatProviderUsageLimit(
                    id="codex",
                    label="Codex",
                    windows=[WebChatProviderUsageWindow(label="Daily", usedPercent=30, remainingPercent=70)],
                )
            ],
            capturedAt="2026-01-01T00:00:00+00:00",
        ),
    )

    response = client.get("/api/web-chat/provider-usage?provider=openai-codex&model=gpt-5.5")

    assert response.status_code == 200
    assert response.json() == {
        "provider": "openai-codex",
        "model": "gpt-5.5",
        "source": "codex",
        "available": True,
        "limits": [
            {
                "id": "codex",
                "label": "Codex",
                "windows": [{"label": "Daily", "usedPercent": 30.0, "remainingPercent": 70.0}],
            }
        ],
        "capturedAt": "2026-01-01T00:00:00+00:00",
    }


def test_codex_provider_usage_maps_rate_limit_payload(monkeypatch):
    from hermes_cli.web_chat_modules import provider_usage

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "rate_limit": {
                    "primary_window": {"used_percent": 20, "limit_window_seconds": 86400, "reset_at": 1767225600},
                    "secondary_window": {"used_percent": 40, "limit_window_seconds": 604800, "reset_at": 1767571200},
                },
                "additional_rate_limits": [
                    {
                        "metered_feature": "codex_other",
                        "limit_name": "Other models",
                        "rate_limit": {
                            "primary_window": {"used_percent": 10, "limit_window_seconds": 86400, "reset_at": 1767225600},
                        },
                    }
                ],
            }

    captured = {}

    def request_get(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        return Response()

    result = provider_usage.codex_provider_usage(resolve_access_token=lambda: "token", request_get=request_get)

    assert captured["url"] == provider_usage.CODEX_USAGE_URL
    assert captured["headers"]["Authorization"] == "Bearer token"
    assert result.available is True
    assert result.limits[0].id == "codex"
    assert result.limits[0].windows[0].label == "Daily"
    assert result.limits[0].windows[0].remainingPercent == 80.0
    assert result.limits[0].windows[1].label == "Weekly"
    assert result.limits[0].windows[1].remainingPercent == 60.0
    assert result.limits[1].id == "codex_other"
    assert result.limits[1].label == "Other models"


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


def test_reorders_managed_workspaces(client, tmp_path, monkeypatch):
    project = tmp_path / "settings-project"
    first = tmp_path / "first"
    second = tmp_path / "second"
    third = tmp_path / "third"
    project.mkdir()
    first.mkdir()
    second.mkdir()
    third.mkdir()
    monkeypatch.setenv("HERMES_WEB_CHAT_PROJECT_ROOT", str(project))

    first_response = client.post("/api/web-chat/workspaces", json={"label": "First", "path": str(first)})
    second_response = client.post("/api/web-chat/workspaces", json={"label": "Second", "path": str(second)})
    third_response = client.post("/api/web-chat/workspaces", json={"label": "Third", "path": str(third)})
    workspace_ids = [
        first_response.json()["workspace"]["id"],
        second_response.json()["workspace"]["id"],
        third_response.json()["workspace"]["id"],
    ]

    response = client.patch("/api/web-chat/workspaces/order", json={"workspaceIds": [workspace_ids[2], workspace_ids[0], workspace_ids[1]]})

    assert response.status_code == 200
    assert [workspace["id"] for workspace in response.json()["workspaces"]] == [workspace_ids[2], workspace_ids[0], workspace_ids[1]]
    assert [workspace["id"] for workspace in client.get("/api/web-chat/workspaces").json()["workspaces"]] == [
        workspace_ids[2],
        workspace_ids[0],
        workspace_ids[1],
    ]

    settings_path = project / ".hermes" / "web-chat" / "settings.json"
    assert [workspace["id"] for workspace in json.loads(settings_path.read_text(encoding="utf-8"))["workspaces"]] == [
        workspace_ids[2],
        workspace_ids[0],
        workspace_ids[1],
    ]


def test_reorder_workspaces_rejects_unknown_or_duplicate_ids(client, tmp_path, monkeypatch):
    project = tmp_path / "settings-project"
    workspace = tmp_path / "workspace"
    project.mkdir()
    workspace.mkdir()
    monkeypatch.setenv("HERMES_WEB_CHAT_PROJECT_ROOT", str(project))

    create = client.post("/api/web-chat/workspaces", json={"label": "Workspace", "path": str(workspace)})
    workspace_id = create.json()["workspace"]["id"]

    duplicate = client.patch("/api/web-chat/workspaces/order", json={"workspaceIds": [workspace_id, workspace_id]})
    unknown = client.patch("/api/web-chat/workspaces/order", json={"workspaceIds": ["missing"]})

    assert duplicate.status_code == 400
    assert duplicate.json()["detail"] == "Workspace IDs must be unique"
    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "Workspace not found"


def test_managed_workspaces_are_stored_in_project_hermes_settings(client, tmp_path, monkeypatch):
    project = tmp_path / "settings-project"
    home = tmp_path / "home"
    workspace = home / "workspace"
    project.mkdir()
    workspace.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
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
                "path": "~/workspace",
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


def test_existing_project_settings_workspace_paths_are_normalized(client, tmp_path, monkeypatch):
    project = tmp_path / "settings-project"
    home = tmp_path / "home"
    workspace = home / "Sites" / "hermesum"
    project.mkdir()
    workspace.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HERMES_WEB_CHAT_PROJECT_ROOT", str(project))

    settings_path = project / ".hermes" / "web-chat" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps({
            "version": 1,
            "workspaces": [{"id": "workspace-id", "label": "Hermesum", "path": "~/Sites/hermesum"}],
        }),
        encoding="utf-8",
    )

    response = client.get("/api/web-chat/workspaces")

    assert response.status_code == 200
    assert response.json()["workspaces"] == [
        {
            "id": "workspace-id",
            "label": "Hermesum",
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
