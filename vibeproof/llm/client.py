"""统一不同模型提供方的同步结构化调用接口。

本模块包含离线可复现的分析、教学和结构校验 Mock，以及 OpenAI-compatible、Ollama 两种真实模型
传输实现；上层 Agent 只依赖统一的 ``ModelClient`` 协议。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from time import sleep
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from vibeproof.config import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_TIMEOUT_SECONDS,
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_TIMEOUT_SECONDS,
    MODEL_MAX_ATTEMPTS,
    MODEL_RETRY_DELAY_SECONDS,
    VIBEPROOF_USER_AGENT,
    ConfigurationError,
    Settings,
)
from vibeproof.llm.structured_output import StructuredOutputSpec


class ModelClientError(RuntimeError):
    """模型请求或返回格式失败，Agent 会把它记录为模型阶段失败。"""


class TransientModelError(ModelClientError):
    """可能在一次有限重试后恢复的临时传输错误。"""


@dataclass(frozen=True)
class ModelMessage:
    """与具体 Provider 无关的一条角色消息。"""

    role: str
    content: str


class ModelClient(Protocol):
    """所有 Agent 依赖的最小模型 Strategy；上层不感知具体 API。"""

    provider: str
    model: str

    def complete(
        self,
        messages: list[ModelMessage],
        *,
        output: StructuredOutputSpec | None = None,
    ) -> str:
        """发送完整消息列表，并返回未经业务解析的模型文本。"""
        ...


class RetryingModelClient:
    """重试装饰器；只处理临时传输错误，不把重试逻辑泄漏给 Agent。"""

    def __init__(
        self,
        client: ModelClient,
        max_attempts: int = MODEL_MAX_ATTEMPTS,
        retry_delay_seconds: float = MODEL_RETRY_DELAY_SECONDS,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds cannot be negative")
        self.client = client
        self.provider = client.provider
        self.model = client.model
        self.max_attempts = max_attempts
        self.retry_delay_seconds = retry_delay_seconds

    def complete(
        self,
        messages: list[ModelMessage],
        *,
        output: StructuredOutputSpec | None = None,
    ) -> str:
        """委托真实客户端，并在限定次数内重试 ``TransientModelError``。"""
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self.client.complete(messages, output=output)
            except TransientModelError:
                if attempt == self.max_attempts:
                    raise
                if self.retry_delay_seconds:
                    sleep(self.retry_delay_seconds)
        raise AssertionError("retry loop ended without returning or raising")


class MockAnalystModelClient:
    """离线 Analyst 替身，用固定规则验证检索动作和引用闭环。"""

    provider = "mock"
    model = "deterministic-analyst-v1"

    def complete(
        self,
        messages: list[ModelMessage],
        *,
        output: StructuredOutputSpec | None = None,
    ) -> str:
        """先依次请求推荐查询，再从已返回证据中组成确定性结论。"""
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
            chunk_id = item.get("evidence_id") or item.get("chunk_id")
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
    """离线 Tutor 替身，把每个代表性源码位置转换成学习单元和题目。"""

    provider = "mock"
    model = "deterministic-tutor-v1"

    def complete(
        self,
        messages: list[ModelMessage],
        *,
        output: StructuredOutputSpec | None = None,
    ) -> str:
        """根据证据列表生成可重复的学习计划，供工作流和测试使用。"""
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
                chunk_id = item.get("evidence_id") or item.get("chunk_id")
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
    """只验证答案评审编排和数据结构，不假装理解用户答案语义。"""

    provider = "mock"
    model = "structure-only-reviewer-v1"

    def complete(
        self,
        messages: list[ModelMessage],
        *,
        output: StructuredOutputSpec | None = None,
    ) -> str:
        """返回不带语义分数的结构化结果，明确要求真实模型才能评分。"""
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
    """把统一消息转换为 OpenAI Chat Completions 请求，并取回 JSON 文本。"""

    provider = "openai-compatible"

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 180.0,
        stream: bool = False,
    ):
        if not model.strip():
            raise ConfigurationError("a model name is required for openai-compatible provider")
        if not base_url.strip():
            raise ConfigurationError("a base URL is required for openai-compatible provider")
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.stream = stream

    def complete(
        self,
        messages: list[ModelMessage],
        *,
        output: StructuredOutputSpec | None = None,
    ) -> str:
        """调用兼容端点，并在传输层得到一个完整的结构化模型响应。"""
        payload = {
            "model": self.model,
            "messages": [{"role": message.role, "content": message.content} for message in messages],
            "temperature": 0,
            "stream": self.stream,
            "response_format": (
                output.openai_response_format() if output is not None else {"type": "json_object"}
            ),
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
    """调用本地 Ollama `/api/chat` 的模型 Strategy。"""

    provider = "ollama"

    def __init__(self, model: str, base_url: str, timeout_seconds: float = 120.0):
        if not model.strip():
            raise ConfigurationError("a model name is required for ollama provider")
        if not base_url.strip():
            raise ConfigurationError("a base URL is required for ollama provider")
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def complete(
        self,
        messages: list[ModelMessage],
        *,
        output: StructuredOutputSpec | None = None,
    ) -> str:
        """请求 Ollama 的非流式 JSON 模式并返回消息正文。"""
        payload = {
            "model": self.model,
            "messages": [{"role": message.role, "content": message.content} for message in messages],
            "stream": False,
            "format": output.schema if output is not None else "json",
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
    settings: Settings | None = None,
) -> ModelClient:
    """依据 Provider 和 Agent 任务创建客户端，是模型实现的唯一组装入口。"""
    settings = settings or Settings.from_env()
    normalized = provider.strip().lower()
    normalized_task = task.strip().lower()
    if normalized_task not in {"analyst", "tutor", "review"}:
        raise ConfigurationError("task must be one of: analyst, tutor, review")
    if normalized == "mock":
        clients = {
            "analyst": MockAnalystModelClient,
            "tutor": MockTutorModelClient,
            "review": MockAnswerReviewModelClient,
        }
        return clients[normalized_task]()
    resolved_model = (model or settings.ai_model).strip()
    if normalized == "openai-compatible":
        resolved_url = (base_url or settings.ai_base_url or DEFAULT_OPENAI_BASE_URL).strip()
        return RetryingModelClient(
            OpenAICompatibleModelClient(
                model=resolved_model,
                base_url=resolved_url,
                api_key=settings.ai_api_key,
                timeout_seconds=settings.ai_timeout_seconds or DEFAULT_OPENAI_TIMEOUT_SECONDS,
            )
        )
    if normalized == "ollama":
        resolved_url = (base_url or settings.ai_base_url or DEFAULT_OLLAMA_BASE_URL).strip()
        return OllamaModelClient(
            model=resolved_model,
            base_url=resolved_url,
            timeout_seconds=settings.ai_timeout_seconds or DEFAULT_OLLAMA_TIMEOUT_SECONDS,
        )
    raise ConfigurationError("provider must be one of: mock, openai-compatible, ollama")


def _http_error(exc: HTTPError) -> ModelClientError:
    detail = exc.read(1_000).decode("utf-8", errors="replace")
    error_type = TransientModelError if exc.code == 429 or 500 <= exc.code < 600 else ModelClientError
    return error_type(f"model endpoint returned HTTP {exc.code}: {detail}")


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
        raise _http_error(exc) from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise TransientModelError(f"model endpoint request failed: {exc}") from exc
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
                    choices = event["choices"]
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise ModelClientError("model stream contained an invalid chat-completions event") from exc
                # 一些 OpenAI-compatible 服务会在正文结束后发送只有 usage、没有候选项的统计事件。
                # 它不属于模型正文，忽略后继续等待 [DONE] 即可。
                if choices == [] and isinstance(event.get("usage"), dict):
                    continue
                try:
                    delta = choices[0]["delta"]
                except (IndexError, KeyError, TypeError) as exc:
                    raise ModelClientError("model stream contained an invalid chat-completions event") from exc
                content = delta.get("content") if isinstance(delta, dict) else None
                if isinstance(content, str):
                    parts.append(content)
    except HTTPError as exc:
        raise _http_error(exc) from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise TransientModelError(f"model endpoint request failed: {exc}") from exc
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
