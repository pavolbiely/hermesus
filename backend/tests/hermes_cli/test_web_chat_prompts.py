"""Tests for web chat interactive run prompts."""

from __future__ import annotations

import sys
import threading
import types


def test_run_prompt_response_resumes_blocking_executor(client, monkeypatch):
    import hermes_cli.web_chat as web_chat
    from hermes_cli.web_chat_modules.models import WebChatPrompt

    prompt_requested = threading.Event()
    seen = {}

    def fake_executor(context, emit):
        prompt = WebChatPrompt(
            id="prompt-1",
            runId=context.run_id,
            sessionId=context.session_id,
            kind="question",
            title="Question from Hermes",
            description="Choose one",
            choices=[
                {"id": "yes", "label": "Yes", "style": "primary"},
                {"id": "no", "label": "No"},
            ],
            createdAt="2026-01-01T00:00:00+00:00",
        )
        prompt_requested.set()
        seen["answer"] = context.request_prompt(prompt, 5)
        return f"answer={seen['answer']}"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))

    response = client.post("/api/web-chat/runs", json={"input": "Ask me"})
    assert response.status_code == 202
    run = response.json()
    assert prompt_requested.wait(timeout=2)

    answer = client.post(
        f"/api/web-chat/runs/{run['runId']}/prompts/prompt-1/response",
        json={"choice": "yes"},
    )
    assert answer.status_code == 200
    assert answer.json()["prompt"]["status"] == "answered"
    assert answer.json()["prompt"]["selectedChoice"] == "yes"

    duplicate = client.post(
        f"/api/web-chat/runs/{run['runId']}/prompts/prompt-1/response",
        json={"choice": "no"},
    )
    assert duplicate.status_code == 409

    with client.stream("GET", f"/api/web-chat/runs/{run['runId']}/events") as stream:
        body = stream.read().decode()

    assert seen["answer"] == "yes"
    assert "event: prompt.requested" in body
    assert "event: prompt.answered" in body
    assert "event: message.completed" in body
    assert "answer=yes" in body
    assert "event: run.completed" in body

    session = client.get(f"/api/web-chat/sessions/{run['sessionId']}")
    assert session.status_code == 200
    assistant_parts = session.json()["messages"][-1]["parts"]
    assert assistant_parts[0]["type"] == "interactive_prompt"
    assert assistant_parts[0]["prompt"]["id"] == "prompt-1"
    assert assistant_parts[0]["prompt"]["status"] == "answered"


def test_run_prompt_timeout_expires_and_fails_safe(client, monkeypatch):
    import hermes_cli.web_chat as web_chat
    from hermes_cli.web_chat_modules.models import WebChatPrompt

    seen = {}

    def fake_executor(context, emit):
        prompt = WebChatPrompt(
            id="prompt-timeout",
            runId=context.run_id,
            sessionId=context.session_id,
            kind="approval",
            title="Allow command?",
            description="Run dangerous command",
            choices=[{"id": "deny", "label": "Deny"}],
            createdAt="2026-01-01T00:00:00+00:00",
        )
        seen["answer"] = context.request_prompt(prompt, 0.01)
        return "timed out"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))

    response = client.post("/api/web-chat/runs", json={"input": "Ask and timeout"})
    assert response.status_code == 202
    run = response.json()

    with client.stream("GET", f"/api/web-chat/runs/{run['runId']}/events") as stream:
        body = stream.read().decode()

    assert seen["answer"] is None
    assert "event: prompt.requested" in body
    assert "event: prompt.expired" in body
    assert '"status":"expired"' in body
    assert "event: run.completed" in body


def test_agent_executor_routes_cross_thread_terminal_approval_to_web_prompt(monkeypatch):
    from hermes_cli.web_chat_modules.agent_runner import agent_executor
    from hermes_cli.web_chat_modules.run_manager import RunContext

    prompts = []
    guard_result = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            pass

        def interrupt(self):
            pass

        def run_conversation(self, prompt, *, conversation_history, task_id):
            def worker():
                from tools.terminal_tool import _check_all_guards

                guard_result.update(_check_all_guards("rm -rf /tmp/hermesum-approval-test/a", "local"))

            thread = threading.Thread(target=worker)
            thread.start()
            thread.join(timeout=2)
            assert not thread.is_alive()
            return {"final_response": "done"}

    def request_prompt(prompt, timeout):
        prompts.append(prompt)
        return "once"

    monkeypatch.setitem(sys.modules, "run_agent", types.SimpleNamespace(AIAgent=FakeAgent))
    monkeypatch.setitem(
        sys.modules,
        "tools.tirith_security",
        types.SimpleNamespace(check_command_security=lambda command: {"action": "allow", "findings": [], "summary": ""}),
    )
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: {})
    monkeypatch.setattr(
        "hermes_cli.runtime_provider.resolve_runtime_provider",
        lambda **_: {"provider": "test", "model": "test-model", "base_url": "http://localhost"},
    )
    monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
    monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
    monkeypatch.delenv("HERMES_EXEC_ASK", raising=False)
    monkeypatch.delenv("HERMES_SESSION_KEY", raising=False)

    context = RunContext(
        run_id="run-approval-thread",
        session_id="session-approval-thread",
        input="trigger approval",
        model="test-model",
        reasoning_effort="none",
        request_prompt=request_prompt,
    )

    assert agent_executor(context, lambda event: None, conversation_history=lambda _: []) == "done"
    assert guard_result["approved"] is True
    assert len(prompts) == 1
    assert prompts[0].kind == "approval"
    assert prompts[0].detail == "rm -rf /tmp/hermesum-approval-test/a"
    assert [choice.id for choice in prompts[0].choices] == ["once", "session", "always", "deny"]


def test_agent_executor_forwards_runtime_status_events(monkeypatch):
    from hermes_cli.web_chat_modules.agent_runner import agent_executor
    from hermes_cli.web_chat_modules.run_manager import RunContext

    events = []
    agent_kwargs = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            agent_kwargs.update(kwargs)
            self.status_callback = kwargs.get("status_callback")

        def run_conversation(self, prompt, *, conversation_history, task_id):
            assert self.status_callback is not None
            self.status_callback("warn", "test warning")
            return {"final_response": "done"}

    monkeypatch.setitem(sys.modules, "run_agent", types.SimpleNamespace(AIAgent=FakeAgent))
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: {})
    monkeypatch.setattr(
        "hermes_cli.runtime_provider.resolve_runtime_provider",
        lambda **_: {"provider": "test", "model": "test-model", "base_url": "http://localhost"},
    )

    context = RunContext(
        run_id="run-status",
        session_id="session-status",
        input="trigger status",
        model="test-model",
        reasoning_effort="none",
    )

    assert agent_executor(context, events.append, conversation_history=lambda _: []) == "done"
    assert "persist_session" not in agent_kwargs
    assert agent_kwargs["session_db"] is None
    assert events == [{
        "type": "agent.status",
        "kind": "warn",
        "message": "test warning",
    }]


def test_agent_executor_does_not_treat_config_base_url_as_explicit_override(monkeypatch):
    from hermes_cli.web_chat_modules.agent_runner import agent_executor
    from hermes_cli.web_chat_modules.run_manager import RunContext

    runtime_kwargs = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            pass

        def run_conversation(self, prompt, *, conversation_history, task_id):
            return {"final_response": "done"}

    def fake_resolve_runtime_provider(**kwargs):
        runtime_kwargs.update(kwargs)
        return {
            "provider": "openai-codex",
            "model": "gpt-5.5",
            "base_url": "https://chatgpt.com/backend-api/codex",
            "api_key": "pool-token",
            "api_mode": "codex_responses",
            "credential_pool": object(),
        }

    monkeypatch.setitem(sys.modules, "run_agent", types.SimpleNamespace(AIAgent=FakeAgent))
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {"model": {"provider": "openai-codex", "base_url": "https://chatgpt.com/backend-api/codex"}},
    )
    monkeypatch.setattr("hermes_cli.runtime_provider.resolve_runtime_provider", fake_resolve_runtime_provider)

    context = RunContext(
        run_id="run-codex-pool",
        session_id="session-codex-pool",
        input="hello",
        model="gpt-5.5",
        reasoning_effort="none",
    )

    assert agent_executor(context, lambda event: None, conversation_history=lambda _: []) == "done"
    assert runtime_kwargs["requested"] == "openai-codex"
    assert "explicit_base_url" not in runtime_kwargs


def test_prompt_response_rejects_ambiguous_choice_and_text(client, monkeypatch):
    import hermes_cli.web_chat as web_chat
    from hermes_cli.web_chat_modules.models import WebChatPrompt

    prompt_requested = threading.Event()

    def fake_executor(context, emit):
        prompt = WebChatPrompt(
            id="prompt-ambiguous",
            runId=context.run_id,
            sessionId=context.session_id,
            kind="question",
            title="Choose",
            choices=[{"id": "yes", "label": "Yes"}],
        )
        prompt_requested.set()
        context.request_prompt(prompt, 5)
        return "done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))
    start = client.post("/api/web-chat/runs", json={"input": "Ask"}).json()
    assert prompt_requested.wait(timeout=2)

    response = client.post(
        f"/api/web-chat/runs/{start['runId']}/prompts/prompt-ambiguous/response",
        json={"choice": "yes", "text": "also text"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Prompt response requires exactly one of choice or text"

    cleanup = client.post(
        f"/api/web-chat/runs/{start['runId']}/prompts/prompt-ambiguous/response",
        json={"choice": "yes"},
    )
    assert cleanup.status_code == 200
    with client.stream("GET", f"/api/web-chat/runs/{start['runId']}/events") as stream:
        stream.read()


def test_prompt_requested_sets_expires_at(client, monkeypatch):
    import hermes_cli.web_chat as web_chat
    from hermes_cli.web_chat_modules.models import WebChatPrompt

    def fake_executor(context, emit):
        prompt = WebChatPrompt(
            id="prompt-expiry",
            runId=context.run_id,
            sessionId=context.session_id,
            kind="approval",
            title="Allow?",
            choices=[{"id": "deny", "label": "Deny"}],
        )
        context.request_prompt(prompt, 0.01)
        return "done"

    monkeypatch.setattr(web_chat, "run_manager", web_chat.RunManager(fake_executor))
    start = client.post("/api/web-chat/runs", json={"input": "Ask"}).json()

    with client.stream("GET", f"/api/web-chat/runs/{start['runId']}/events") as stream:
        body = stream.read().decode()

    requested_line = next(line for line in body.splitlines() if line.startswith("data: ") and "prompt.requested" in line)
    prompt = __import__("json").loads(requested_line.removeprefix("data: "))["prompt"]
    assert prompt["expiresAt"] is not None
