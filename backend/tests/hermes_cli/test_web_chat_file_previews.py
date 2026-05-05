"""Tests for local file preview endpoints."""

from __future__ import annotations

from types import SimpleNamespace

from web_chat_test_helpers import git_repo


def post_preview(client, path: str, workspace: str | None):
    payload = {"path": path}
    if workspace is not None:
        payload["workspace"] = workspace
    return client.post("/api/web-chat/file-preview", json=payload)


def post_resolve(client, paths: list[str], workspace: str | None):
    payload = {"paths": paths}
    if workspace is not None:
        payload["workspace"] = workspace
    return client.post("/api/web-chat/file-preview/resolve", json=payload)


def stub_active_profile(monkeypatch, profile_dir, name: str = "main"):
    from hermes_cli import web_chat

    monkeypatch.setattr(web_chat, "_profile_dependencies", lambda: (
        lambda: name,
        lambda: [SimpleNamespace(name=name, path=profile_dir)],
        lambda requested: requested == name,
        lambda requested: str(profile_dir),
        lambda requested: None,
        lambda requested: None,
    ))


def test_skill_file_preview_loads_skill_from_active_profile(client, monkeypatch, tmp_path):
    profile = tmp_path / "profiles" / "main"
    skill = profile / "skills" / "software-development" / "demo-skill"
    skill.mkdir(parents=True)
    skill_file = skill / "SKILL.md"
    skill_file.write_text("---\nname: demo-skill\n---\n\n# Demo\n", encoding="utf-8")
    stub_active_profile(monkeypatch, profile)

    response = client.post("/api/web-chat/skill-file-preview", json={"name": "demo-skill"})

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == str(skill_file)
    assert body["requestedPath"] == "demo-skill/SKILL.md"
    assert body["relativePath"] == "demo-skill/SKILL.md"
    assert body["name"] == "SKILL.md"
    assert body["mediaType"] == "text/markdown"
    assert body["language"] == "markdown"
    assert body["content"] == "---\nname: demo-skill\n---\n\n# Demo\n"


def test_skill_file_preview_rejects_path_traversal(client, monkeypatch, tmp_path):
    profile = tmp_path / "profiles" / "main"
    skill = profile / "skills" / "demo-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Demo\n", encoding="utf-8")
    stub_active_profile(monkeypatch, profile)

    response = client.post("/api/web-chat/skill-file-preview", json={"name": "demo-skill", "filePath": "../secret.md"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Skill file is outside the selected skill"


def test_file_preview_loads_relative_markdown_from_workspace(client, tmp_path):
    repo = git_repo(tmp_path)
    plan = repo / ".hermes" / "plans" / "example.md"
    plan.parent.mkdir(parents=True)
    plan.write_text("# Plan\n\n- item\n", encoding="utf-8")

    response = post_preview(client, ".hermes/plans/example.md", str(repo))

    assert response.status_code == 200
    body = response.json()
    assert body["requestedPath"] == ".hermes/plans/example.md"
    assert body["path"] == str(plan)
    assert body["relativePath"] == ".hermes/plans/example.md"
    assert body["name"] == "example.md"
    assert body["mediaType"] == "text/markdown"
    assert body["language"] == "markdown"
    assert body["content"] == "# Plan\n\n- item\n"
    assert body["previewable"] is True
    assert body["truncated"] is False


def test_file_preview_loads_relative_path_from_git_root_when_workspace_is_subdirectory(client, tmp_path):
    repo = git_repo(tmp_path)
    subdir = repo / "apps" / "web"
    subdir.mkdir(parents=True)
    config = repo / "config" / "app.yaml"
    config.parent.mkdir()
    config.write_text("name: demo\n", encoding="utf-8")

    response = post_preview(client, "config/app.yaml", str(subdir))

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == str(config)
    assert body["relativePath"] == "config/app.yaml"
    assert body["language"] == "yaml"
    assert body["content"] == "name: demo\n"


def test_file_preview_allows_absolute_path_inside_workspace(client, tmp_path):
    repo = git_repo(tmp_path)
    source = repo / "src" / "foo.ts"
    source.parent.mkdir()
    source.write_text("export const foo = 1\n", encoding="utf-8")

    response = post_preview(client, str(source), str(repo))

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == str(source)
    assert body["relativePath"] == "src/foo.ts"
    assert body["language"] == "typescript"


def test_file_preview_detects_vue_sources(client, tmp_path):
    repo = git_repo(tmp_path)
    source = repo / "components" / "Example.vue"
    source.parent.mkdir()
    source.write_text("<template><div>Hello</div></template>\n", encoding="utf-8")

    response = post_preview(client, "components/Example.vue", str(repo))

    assert response.status_code == 200
    body = response.json()
    assert body["mediaType"] == "text/vue"
    assert body["language"] == "vue"
    assert body["previewable"] is True


def test_file_preview_rejects_parent_traversal_outside_workspace(client, tmp_path):
    repo = git_repo(tmp_path)
    secret = tmp_path / "secret.md"
    secret.write_text("secret", encoding="utf-8")

    response = post_preview(client, "../secret.md", str(repo))

    assert response.status_code == 400
    assert response.json()["detail"] == "File is outside the selected workspace"


def test_file_preview_rejects_absolute_path_outside_workspace(client, tmp_path):
    repo = git_repo(tmp_path)
    secret = tmp_path / "secret.md"
    secret.write_text("secret", encoding="utf-8")

    response = post_preview(client, str(secret), str(repo))

    assert response.status_code == 400
    assert response.json()["detail"] == "File is outside the selected workspace"


def test_file_preview_missing_file_returns_404(client, tmp_path):
    repo = git_repo(tmp_path)

    response = post_preview(client, "missing/example.md", str(repo))

    assert response.status_code == 404
    assert response.json()["detail"] == "File not found"


def test_file_preview_binary_file_returns_non_previewable_metadata(client, tmp_path):
    repo = git_repo(tmp_path)
    image = repo / "assets" / "logo.png"
    image.parent.mkdir()
    image.write_bytes(b"\x89PNG\r\n\x1a\n")

    response = post_preview(client, "assets/logo.png", str(repo))

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == str(image)
    assert body["mediaType"] == "image/png"
    assert body["previewable"] is False
    assert "content" not in body
    assert body["reason"] == "File type cannot be previewed as text"


def test_file_preview_allows_extensionless_utf8_text(client, tmp_path):
    repo = git_repo(tmp_path)
    makefile = repo / "Makefile"
    makefile.write_text("test:\n\tpytest\n", encoding="utf-8")

    response = post_preview(client, "Makefile", str(repo))

    assert response.status_code == 200
    body = response.json()
    assert body["previewable"] is True
    assert body["content"] == "test:\n\tpytest\n"
    assert body["language"] == "makefile"


def test_file_preview_large_text_is_truncated(client, tmp_path):
    repo = git_repo(tmp_path)
    source = repo / "large.txt"
    source.write_text("a" * (256 * 1024 + 100), encoding="utf-8")

    response = post_preview(client, "large.txt", str(repo))

    assert response.status_code == 200
    body = response.json()
    assert body["previewable"] is True
    assert body["truncated"] is True
    assert len(body["content"].encode("utf-8")) == 256 * 1024


def test_file_preview_requires_workspace_for_relative_paths(client):
    response = post_preview(client, "README.md", None)

    assert response.status_code == 400
    assert response.json()["detail"] == "Select a workspace before previewing relative files"


def test_file_preview_resolve_returns_only_existing_workspace_files(client, tmp_path):
    repo = git_repo(tmp_path)
    source = repo / "src" / "foo.ts"
    source.parent.mkdir()
    source.write_text("export const foo = 1\n", encoding="utf-8")
    outside = tmp_path / "secret.md"
    outside.write_text("secret", encoding="utf-8")

    response = post_resolve(client, ["src/foo.ts", "missing.md", str(outside), "src/foo.ts"], str(repo))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["requestedPath"] == "src/foo.ts"
    assert body[0]["path"] == str(source)
    assert body[0]["relativePath"] == "src/foo.ts"
    assert body[0]["exists"] is True
    assert body[0]["language"] == "typescript"


def test_file_preview_resolve_uses_git_root_for_subdirectory_workspace(client, tmp_path):
    repo = git_repo(tmp_path)
    subdir = repo / "apps" / "web"
    subdir.mkdir(parents=True)
    config = repo / "config" / "app.yaml"
    config.parent.mkdir()
    config.write_text("name: demo\n", encoding="utf-8")

    response = post_resolve(client, ["config/app.yaml"], str(subdir))

    assert response.status_code == 200
    assert response.json()[0]["relativePath"] == "config/app.yaml"
