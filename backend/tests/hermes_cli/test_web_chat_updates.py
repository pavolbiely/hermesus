from __future__ import annotations


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
