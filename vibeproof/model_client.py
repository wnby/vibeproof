from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ModelClientError(RuntimeError):
    pass


class ModelConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ModelMessage:
    role: str
    content: str


class ModelClient(Protocol):
    provider: str
    model: str

    def complete(self, messages: list[ModelMessage]) -> str: ...


class MockAnalystModelClient:
    provider = "mock"
    model = "deterministic-analyst-v1"

    def complete(self, messages: list[ModelMessage]) -> str:
        state = _extract_state(messages)
        completed = set(state.get("completed_queries", []))
        recommended = state.get("recommended_queries", [])
        for query in recommended[:3]:
            if query not in completed:
                return json.dumps({"action": "SEARCH_SOURCE", "query": query})

        evidence = state.get("evidence", [])
        repository = state.get("repository", {})
        entrypoints = set(repository.get("entrypoints", [])) if isinstance(repository, dict) else set()
        claims = []
        seen_chunks: set[str] = set()
        for item in evidence:
            chunk_id = item.get("chunk_id")
            if not chunk_id or chunk_id in seen_chunks:
                continue
            seen_chunks.add(chunk_id)
            path = item.get("path", "unknown")
            symbol = item.get("symbol")
            start_line = item.get("start_line", 1)
            end_line = item.get("end_line", start_line)
            subject = symbol or path
            claims.append(
                {
                    "claim": f"{subject} is present in {path} at lines {start_line}-{end_line}.",
                    "claim_type": "ENTRYPOINT" if path in entrypoints else "COMPONENT",
                    "evidence_ids": [chunk_id],
                    "confidence": 1.0,
                }
            )
            if len(claims) >= 5:
                break

        repository_name = (
            repository.get("repository_name", "repository") if isinstance(repository, dict) else "repository"
        )
        if claims:
            summary = f"Offline evidence pass identified {len(claims)} source-grounded locations in {repository_name}."
            unresolved = ["A semantic architecture narrative requires a configured language model."]
        else:
            summary = f"Offline evidence pass found no source evidence for {repository_name}."
            unresolved = ["No evidence was retrieved; review the index and recommended queries."]
        return json.dumps(
            {
                "action": "FINAL_ANSWER",
                "summary": summary,
                "claims": claims,
                "unresolved_questions": unresolved,
            }
        )


class OpenAICompatibleModelClient:
    provider = "openai-compatible"

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
    ):
        if not model.strip():
            raise ModelConfigurationError("a model name is required for openai-compatible provider")
        if not base_url.strip():
            raise ModelConfigurationError("a base URL is required for openai-compatible provider")
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def complete(self, messages: list[ModelMessage]) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": message.role, "content": message.content} for message in messages],
            "temperature": 0,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = _post_json(
            f"{self.base_url}/chat/completions",
            payload,
            headers=headers,
            timeout_seconds=self.timeout_seconds,
        )
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelClientError("openai-compatible response did not contain message content") from exc
        if not isinstance(content, str) or not content.strip():
            raise ModelClientError("openai-compatible response contained empty message content")
        return content


class OllamaModelClient:
    provider = "ollama"

    def __init__(self, model: str, base_url: str, timeout_seconds: float = 120.0):
        if not model.strip():
            raise ModelConfigurationError("a model name is required for ollama provider")
        if not base_url.strip():
            raise ModelConfigurationError("a base URL is required for ollama provider")
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def complete(self, messages: list[ModelMessage]) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": message.role, "content": message.content} for message in messages],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }
        response = _post_json(
            f"{self.base_url}/api/chat",
            payload,
            headers={"Content-Type": "application/json"},
            timeout_seconds=self.timeout_seconds,
        )
        try:
            content = response["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise ModelClientError("Ollama response did not contain message content") from exc
        if not isinstance(content, str) or not content.strip():
            raise ModelClientError("Ollama response contained empty message content")
        return content


def create_model_client(
    provider: str,
    model: str | None = None,
    base_url: str | None = None,
) -> ModelClient:
    normalized = provider.strip().lower()
    if normalized == "mock":
        return MockAnalystModelClient()
    resolved_model = (model or os.getenv("VIBEPROOF_AI_MODEL", "")).strip()
    if normalized == "openai-compatible":
        configured_url = os.getenv("VIBEPROOF_AI_BASE_URL", "").strip()
        resolved_url = (base_url or configured_url or "https://api.openai.com/v1").strip()
        return OpenAICompatibleModelClient(
            model=resolved_model,
            base_url=resolved_url,
            api_key=os.getenv("VIBEPROOF_AI_API_KEY") or None,
        )
    if normalized == "ollama":
        configured_url = os.getenv("VIBEPROOF_AI_BASE_URL", "").strip()
        resolved_url = (base_url or configured_url or "http://127.0.0.1:11434").strip()
        return OllamaModelClient(model=resolved_model, base_url=resolved_url)
    raise ModelConfigurationError("provider must be one of: mock, openai-compatible, ollama")


def _post_json(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
    timeout_seconds: float,
) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - URL is explicit operator config
            data = response.read(2_000_000)
    except HTTPError as exc:
        detail = exc.read(1_000).decode("utf-8", errors="replace")
        raise ModelClientError(f"model endpoint returned HTTP {exc.code}: {detail}") from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise ModelClientError(f"model endpoint request failed: {exc}") from exc
    try:
        decoded = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModelClientError("model endpoint returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise ModelClientError("model endpoint returned a non-object JSON response")
    return decoded


def _extract_state(messages: list[ModelMessage]) -> dict[str, object]:
    marker = "STATE_JSON:\n"
    for message in reversed(messages):
        if message.role == "user" and marker in message.content:
            raw = message.content.split(marker, 1)[1]
            try:
                state = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ModelClientError("mock provider received invalid analyst state") from exc
            if isinstance(state, dict):
                return state
    raise ModelClientError("mock provider did not receive analyst state")
