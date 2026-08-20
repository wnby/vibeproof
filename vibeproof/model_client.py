"""统一不同模型提供方的同步结构化调用接口。

本模块包含离线可复现的分析、教学和结构校验 Mock，以及 OpenAI-compatible、Ollama 两种真实模型
传输实现；上层 Agent 只依赖统一的 ``ModelClient`` 协议。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

VIBEPROOF_USER_AGENT = "VibeProof/0.1 (+https://github.com/wnby/vibeproof)"


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


class MockTutorModelClient:
    provider = "mock"
    model = "deterministic-tutor-v1"

    def complete(self, messages: list[ModelMessage]) -> str:
        state = _extract_tutor_state(messages)
        evidence = state.get("evidence", [])
        repository = state.get("repository", {})
        repository_name = (
            repository.get("repository_name", "repository") if isinstance(repository, dict) else "repository"
        )
        units: list[dict[str, object]] = []
        questions: list[dict[str, object]] = []
        seen_paths: set[str] = set()
        if isinstance(evidence, list):
            for item in evidence:
                if not isinstance(item, dict):
                    continue
                chunk_id = item.get("chunk_id")
                path = str(item.get("path", "unknown"))
                if not isinstance(chunk_id, str) or not chunk_id or path in seen_paths:
                    continue
                seen_paths.add(path)
                sequence = len(units) + 1
                subject = str(item.get("symbol") or path)
                units.append(
                    {
                        "sequence": sequence,
                        "title": f"Understand {subject}",
                        "objective": f"Explain the responsibility of {subject} and its role in {path}.",
                        "why_it_matters": "This source location is part of the evidence-backed takeover path.",
                        "exercise": f"Trace one caller or dependency of {subject} and summarize the flow.",
                        "evidence_ids": [chunk_id],
                    }
                )
                questions.append(
                    {
                        "question_id": f"unit-{sequence}-q1",
                        "unit_sequence": sequence,
                        "difficulty": "BASIC" if sequence == 1 else "TRACE",
                        "prompt": f"What responsibility does {subject} have in {path}, based on the cited source?",
                        "evaluation_points": [
                            "Identify the source responsibility",
                            "Explain one relevant control or data-flow connection",
                            "Ground the answer in the cited line range",
                        ],
                        "evidence_ids": [chunk_id],
                    }
                )
                if len(units) >= 4:
                    break
        return json.dumps(
            {
                "summary": f"A staged source-grounded takeover path for {repository_name}.",
                "units": units,
                "questions": questions,
            }
        )


class MockAnswerReviewModelClient:
    """Validate answer-review orchestration without pretending to understand the answer."""

    provider = "mock"
    model = "structure-only-reviewer-v1"

    def complete(self, messages: list[ModelMessage]) -> str:
        state = _extract_review_state(messages)
        question = state.get("question", {})
        question_id = question.get("question_id", "unknown") if isinstance(question, dict) else "unknown"
        evidence_ids = question.get("evidence_ids", []) if isinstance(question, dict) else []
        return json.dumps(
            {
                "question_id": question_id,
                "score": None,
                "feedback": "Structure-only mock review; semantic scoring requires a configured model.",
                "strengths": [],
                "gaps": [],
                "evidence_ids": evidence_ids,
            }
        )


class OpenAICompatibleModelClient:
    provider = "openai-compatible"

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 180.0,
        stream: bool = True,
    ):
        if not model.strip():
            raise ModelConfigurationError("a model name is required for openai-compatible provider")
        if not base_url.strip():
            raise ModelConfigurationError("a base URL is required for openai-compatible provider")
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.stream = stream

    def complete(self, messages: list[ModelMessage]) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": message.role, "content": message.content} for message in messages],
            "temperature": 0,
            "stream": self.stream,
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": VIBEPROOF_USER_AGENT,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.stream:
            return _post_openai_sse(
                f"{self.base_url}/chat/completions",
                payload,
                headers=headers,
                timeout_seconds=self.timeout_seconds,
            )
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
            headers={"Content-Type": "application/json", "User-Agent": VIBEPROOF_USER_AGENT},
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
    *,
    task: str = "analyst",
) -> ModelClient:
    normalized = provider.strip().lower()
    normalized_task = task.strip().lower()
    if normalized_task not in {"analyst", "tutor", "review"}:
        raise ModelConfigurationError("task must be one of: analyst, tutor, review")
    if normalized == "mock":
        clients = {
            "analyst": MockAnalystModelClient,
            "tutor": MockTutorModelClient,
            "review": MockAnswerReviewModelClient,
        }
        return clients[normalized_task]()
    resolved_model = (model or os.getenv("VIBEPROOF_AI_MODEL", "")).strip()
    configured_timeout = os.getenv("VIBEPROOF_AI_TIMEOUT_SECONDS", "").strip()
    try:
        resolved_timeout = float(configured_timeout) if configured_timeout else None
    except ValueError as exc:
        raise ModelConfigurationError("VIBEPROOF_AI_TIMEOUT_SECONDS must be a number") from exc
    if resolved_timeout is not None and resolved_timeout <= 0:
        raise ModelConfigurationError("VIBEPROOF_AI_TIMEOUT_SECONDS must be greater than zero")
    if normalized == "openai-compatible":
        configured_url = os.getenv("VIBEPROOF_AI_BASE_URL", "").strip()
        resolved_url = (base_url or configured_url or "https://api.openai.com/v1").strip()
        return OpenAICompatibleModelClient(
            model=resolved_model,
            base_url=resolved_url,
            api_key=os.getenv("VIBEPROOF_AI_API_KEY") or None,
            timeout_seconds=resolved_timeout or 180.0,
        )
    if normalized == "ollama":
        configured_url = os.getenv("VIBEPROOF_AI_BASE_URL", "").strip()
        resolved_url = (base_url or configured_url or "http://127.0.0.1:11434").strip()
        return OllamaModelClient(
            model=resolved_model,
            base_url=resolved_url,
            timeout_seconds=resolved_timeout or 120.0,
        )
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


def _post_openai_sse(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
    timeout_seconds: float,
) -> str:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    parts: list[str] = []
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - URL is explicit operator config
            for raw_line in response:
                try:
                    line = raw_line.decode("utf-8").strip()
                except UnicodeDecodeError as exc:
                    raise ModelClientError("model stream contained invalid UTF-8") from exc
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                    delta = event["choices"][0]["delta"]
                except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
                    raise ModelClientError("model stream contained an invalid chat-completions event") from exc
                content = delta.get("content") if isinstance(delta, dict) else None
                if isinstance(content, str):
                    parts.append(content)
    except HTTPError as exc:
        detail = exc.read(1_000).decode("utf-8", errors="replace")
        raise ModelClientError(f"model endpoint returned HTTP {exc.code}: {detail}") from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise ModelClientError(f"model endpoint request failed: {exc}") from exc
    content = "".join(parts)
    if not content.strip():
        raise ModelClientError("model stream contained no message content")
    return content


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


def _extract_tutor_state(messages: list[ModelMessage]) -> dict[str, object]:
    marker = "TUTOR_STATE_JSON:\n"
    for message in reversed(messages):
        if message.role == "user" and marker in message.content:
            raw = message.content.split(marker, 1)[1]
            try:
                state = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ModelClientError("mock provider received invalid tutor state") from exc
            if isinstance(state, dict):
                return state
    raise ModelClientError("mock provider did not receive tutor state")


def _extract_review_state(messages: list[ModelMessage]) -> dict[str, object]:
    marker = "ANSWER_REVIEW_STATE_JSON:\n"
    for message in reversed(messages):
        if message.role == "user" and marker in message.content:
            raw = message.content.split(marker, 1)[1]
            try:
                state = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ModelClientError("mock provider received invalid answer-review state") from exc
            if isinstance(state, dict):
                return state
    raise ModelClientError("mock provider did not receive answer-review state")
