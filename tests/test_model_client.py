import json

import pytest

from vibeproof.model_client import (
    MockAnalystModelClient,
    MockAnswerReviewModelClient,
    MockTutorModelClient,
    ModelConfigurationError,
    ModelMessage,
    OllamaModelClient,
    OpenAICompatibleModelClient,
    create_model_client,
)


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

    with pytest.raises(ModelConfigurationError, match="model name is required"):
        create_model_client("ollama")


def test_model_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ModelConfigurationError, match="provider must be one of"):
        create_model_client("unknown")


def test_model_factory_uses_default_ollama_url_when_environment_is_blank(monkeypatch) -> None:
    monkeypatch.setenv("VIBEPROOF_AI_MODEL", "local-model")
    monkeypatch.setenv("VIBEPROOF_AI_BASE_URL", "")

    client = create_model_client("ollama")

    assert isinstance(client, OllamaModelClient)
    assert client.base_url == "http://127.0.0.1:11434"


def test_openai_compatible_client_uses_chat_completion_shape(monkeypatch) -> None:
    captured = {}

    def fake_post(url, payload, headers, timeout_seconds):
        captured.update(url=url, payload=payload, headers=headers, timeout=timeout_seconds)
        return {"choices": [{"message": {"content": '{"action":"FINAL_ANSWER"}'}}]}

    monkeypatch.setattr("vibeproof.model_client._post_json", fake_post)
    client = OpenAICompatibleModelClient(
        model="test-model",
        base_url="https://models.example/v1/",
        api_key="secret-test-key",
    )

    content = client.complete([ModelMessage(role="user", content="hello")])

    assert content == '{"action":"FINAL_ANSWER"}'
    assert captured["url"] == "https://models.example/v1/chat/completions"
    assert captured["payload"]["messages"] == [{"role": "user", "content": "hello"}]
    assert captured["headers"]["Authorization"] == "Bearer secret-test-key"


def test_ollama_client_requests_non_streaming_json(monkeypatch) -> None:
    captured = {}

    def fake_post(url, payload, headers, timeout_seconds):
        captured.update(url=url, payload=payload, headers=headers, timeout=timeout_seconds)
        return {"message": {"content": '{"action":"SEARCH_SOURCE","query":"main"}'}}

    monkeypatch.setattr("vibeproof.model_client._post_json", fake_post)
    client = OllamaModelClient(model="local-model", base_url="http://127.0.0.1:11434/")

    content = client.complete([ModelMessage(role="system", content="policy")])

    assert "SEARCH_SOURCE" in content
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["format"] == "json"
