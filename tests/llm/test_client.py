"""验证统一模型客户端及不同提供方的请求契约。

测试覆盖三个任务专用 Mock、模型工厂配置、OpenAI-compatible 请求结构和 Ollama JSON 模式，保证上层
Agent 能通过一致接口切换离线演示与真实模型。
"""

import json

import pytest

from vibeproof.config import ConfigurationError
from vibeproof.core.models import AgentAction
from vibeproof.llm.client import (
    MockAnalystModelClient,
    MockAnswerReviewModelClient,
    MockTutorModelClient,
    ModelClientError,
    ModelMessage,
    OllamaModelClient,
    OpenAICompatibleModelClient,
    RetryingModelClient,
    TransientModelError,
    create_model_client,
)
from vibeproof.llm.structured_output import StructuredOutputSpec


def _state_message(state: dict[str, object]) -> list[ModelMessage]:
    return [ModelMessage(role="user", content=f"STATE_JSON:\n{json.dumps(state)}")]


def test_mock_provider_requests_recommended_query() -> None:
    client = MockAnalystModelClient()
    state = {
        "repository": {"repository_name": "demo"},
        "recommended_queries": ["main.py"],
        "completed_queries": [],
        "evidence": [],
    }

    action = json.loads(client.complete(_state_message(state)))

    assert action == {"action": "SEARCH_SOURCE", "query": "main.py"}


def test_mock_provider_finishes_with_observed_evidence() -> None:
    client = MockAnalystModelClient()
    state = {
        "repository": {"repository_name": "demo"},
        "recommended_queries": ["main.py"],
        "completed_queries": ["main.py"],
        "evidence": [
            {
                "chunk_id": "chunk:one",
                "path": "main.py",
                "symbol": "main",
                "start_line": 1,
                "end_line": 3,
            }
        ],
    }

    action = json.loads(client.complete(_state_message(state)))

    assert action["action"] == "FINAL_ANSWER"
    assert action["claims"][0]["evidence_ids"] == ["chunk:one"]


def test_model_factory_creates_task_specific_mock_tutor() -> None:
    client = create_model_client("mock", task="tutor")

    assert isinstance(client, MockTutorModelClient)
    assert client.model == "deterministic-tutor-v1"


def test_model_factory_creates_structure_only_mock_reviewer() -> None:
    client = create_model_client("mock", task="review")
    state = {
        "question": {"question_id": "q1", "evidence_ids": ["chunk:one"]},
        "learner_answer": "An answer",
        "source_evidence": [],
    }

    result = json.loads(
        client.complete(
            [ModelMessage(role="user", content=f"ANSWER_REVIEW_STATE_JSON:\n{json.dumps(state)}")]
        )
    )

    assert isinstance(client, MockAnswerReviewModelClient)
    assert result["score"] is None
    assert result["evidence_ids"] == ["chunk:one"]


def test_model_factory_requires_model_for_network_provider(monkeypatch) -> None:
    monkeypatch.delenv("VIBEPROOF_AI_MODEL", raising=False)

    with pytest.raises(ConfigurationError, match="model name is required"):
        create_model_client("ollama")


def test_model_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ConfigurationError, match="provider must be one of"):
        create_model_client("unknown")


def test_model_factory_uses_default_ollama_url_when_environment_is_blank(monkeypatch) -> None:
    monkeypatch.setenv("VIBEPROOF_AI_MODEL", "local-model")
    monkeypatch.setenv("VIBEPROOF_AI_BASE_URL", "")

    client = create_model_client("ollama")

    assert isinstance(client, OllamaModelClient)
    assert client.base_url == "http://127.0.0.1:11434"


def test_model_factory_uses_configured_network_timeout(monkeypatch) -> None:
    monkeypatch.setenv("VIBEPROOF_AI_MODEL", "relay-model")
    monkeypatch.setenv("VIBEPROOF_AI_TIMEOUT_SECONDS", "240")

    client = create_model_client("openai-compatible", base_url="https://models.example/v1")

    assert isinstance(client, RetryingModelClient)
    assert isinstance(client.client, OpenAICompatibleModelClient)
    assert client.client.timeout_seconds == 240


def test_model_factory_rejects_invalid_network_timeout(monkeypatch) -> None:
    monkeypatch.setenv("VIBEPROOF_AI_MODEL", "relay-model")
    monkeypatch.setenv("VIBEPROOF_AI_TIMEOUT_SECONDS", "never")

    with pytest.raises(ConfigurationError, match="must be a number"):
        create_model_client("openai-compatible")


def test_openai_compatible_client_uses_chat_completion_shape(monkeypatch) -> None:
    captured = {}

    def fake_post(url, payload, headers, timeout_seconds):
        captured.update(url=url, payload=payload, headers=headers, timeout=timeout_seconds)
        return {"choices": [{"message": {"content": '{"action":"FINAL_ANSWER"}'}}]}

    monkeypatch.setattr("vibeproof.llm.client._post_json", fake_post)
    client = OpenAICompatibleModelClient(
        model="test-model",
        base_url="https://models.example/v1/",
        api_key="secret-test-key",
        stream=False,
    )

    content = client.complete([ModelMessage(role="user", content="hello")])

    assert content == '{"action":"FINAL_ANSWER"}'
    assert captured["url"] == "https://models.example/v1/chat/completions"
    assert captured["payload"]["messages"] == [{"role": "user", "content": "hello"}]
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["headers"]["Authorization"] == "Bearer secret-test-key"
    assert captured["headers"]["User-Agent"].startswith("VibeProof/")


def test_openai_compatible_client_assembles_streamed_content(monkeypatch) -> None:
    captured = {}

    def fake_stream(url, payload, headers, timeout_seconds):
        captured.update(url=url, payload=payload, headers=headers, timeout=timeout_seconds)
        return '{"action":"FINAL_ANSWER"}'

    monkeypatch.setattr("vibeproof.llm.client._post_openai_sse", fake_stream)
    client = OpenAICompatibleModelClient(
        model="test-model",
        base_url="https://models.example/v1",
        stream=True,
    )
    output = StructuredOutputSpec.from_model("agent_action", AgentAction)

    content = client.complete([ModelMessage(role="user", content="hello")], output=output)

    assert content == '{"action":"FINAL_ANSWER"}'
    assert captured["payload"]["stream"] is True
    assert captured["payload"]["response_format"] == output.openai_response_format()
    assert captured["url"] == "https://models.example/v1/chat/completions"


def test_openai_sse_parser_joins_delta_content(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def __iter__(self):
            return iter(
                [
                    b'data: {"choices":[{"delta":{"content":"{\\"ok\\":"}}]}\n',
                    b'data: {"choices":[{"delta":{"content":"true}"}}]}\n',
                    b'data: {"choices":[],"usage":{"prompt_tokens":8,"completion_tokens":3}}\n',
                    b"data: [DONE]\n",
                ]
            )

    monkeypatch.setattr("vibeproof.llm.client.urlopen", lambda request, timeout: FakeResponse())
    client = OpenAICompatibleModelClient(
        model="test-model",
        base_url="https://models.example/v1",
        stream=True,
    )

    assert client.complete([ModelMessage(role="user", content="hello")]) == '{"ok":true}'


def test_retrying_client_retries_one_transient_failure() -> None:
    class FlakyClient:
        provider = "test"
        model = "flaky"

        def __init__(self):
            self.calls = 0

        def complete(self, messages, *, output=None):
            self.calls += 1
            if self.calls == 1:
                raise TransientModelError("temporary failure")
            return '{"ok":true}'

    base = FlakyClient()
    client = RetryingModelClient(base, retry_delay_seconds=0)

    assert client.complete([ModelMessage(role="user", content="hello")]) == '{"ok":true}'
    assert base.calls == 2


def test_retrying_client_does_not_retry_permanent_errors() -> None:
    class InvalidResponseClient:
        provider = "test"
        model = "invalid"

        def __init__(self):
            self.calls = 0

        def complete(self, messages, *, output=None):
            self.calls += 1
            raise ModelClientError("invalid response")

    base = InvalidResponseClient()
    client = RetryingModelClient(base, retry_delay_seconds=0)

    with pytest.raises(ModelClientError, match="invalid response"):
        client.complete([ModelMessage(role="user", content="hello")])
    assert base.calls == 1


def test_retrying_client_stops_after_two_transient_failures() -> None:
    class OfflineClient:
        provider = "test"
        model = "offline"

        def __init__(self):
            self.calls = 0

        def complete(self, messages, *, output=None):
            self.calls += 1
            raise TransientModelError("still offline")

    base = OfflineClient()
    client = RetryingModelClient(base, retry_delay_seconds=0)

    with pytest.raises(TransientModelError, match="still offline"):
        client.complete([ModelMessage(role="user", content="hello")])
    assert base.calls == 2


def test_ollama_client_requests_non_streaming_json(monkeypatch) -> None:
    captured = {}

    def fake_post(url, payload, headers, timeout_seconds):
        captured.update(url=url, payload=payload, headers=headers, timeout=timeout_seconds)
        return {"message": {"content": '{"action":"SEARCH_SOURCE","query":"main"}'}}

    monkeypatch.setattr("vibeproof.llm.client._post_json", fake_post)
    client = OllamaModelClient(model="local-model", base_url="http://127.0.0.1:11434/")

    content = client.complete([ModelMessage(role="system", content="policy")])

    assert "SEARCH_SOURCE" in content
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["format"] == "json"
    assert captured["headers"]["User-Agent"].startswith("VibeProof/")
