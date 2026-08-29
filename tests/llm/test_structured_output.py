"""验证真实模型 JSON 包装的有限兼容和拒绝边界。

测试确认裸对象、Markdown JSON 代码块和对象前说明可以规范化，同时空输出、数组、不完整 JSON、多个
对象或对象后附加文字仍会失败，避免兼容层绕过 Pydantic 数据契约。
"""

import json

import pytest

from vibeproof.core.models import AgentAction
from vibeproof.llm.structured_output import (
    StructuredOutputError,
    StructuredOutputSpec,
    normalize_json_object,
)


def test_structured_output_spec_derives_strict_schema_from_pydantic_model() -> None:
    spec = StructuredOutputSpec.from_model("agent_action", AgentAction)

    assert spec.schema["required"] == list(spec.schema["properties"])
    assert spec.schema["additionalProperties"] is False
    claim_schema = spec.schema["$defs"]["ClaimDraft"]
    assert claim_schema["required"] == list(claim_schema["properties"])
    assert "default" not in claim_schema["properties"]["confidence"]
    assert spec.openai_response_format()["json_schema"]["strict"] is True


@pytest.mark.parametrize(
    "raw",
    [
        '{"action":"SEARCH_SOURCE","query":"main"}',
        '```json\n{"action":"SEARCH_SOURCE","query":"main"}\n```',
        'Here is the requested object:\n{"action":"SEARCH_SOURCE","query":"main"}',
        'Here is the requested object:\n```json\n{"action":"SEARCH_SOURCE","query":"main"}\n```',
    ],
)
def test_normalize_json_object_accepts_one_wrapped_object(raw: str) -> None:
    normalized = json.loads(normalize_json_object(raw))

    assert normalized == {"action": "SEARCH_SOURCE", "query": "main"}


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "[]",
        "```json\n{\"ok\":true}",
        '{"ok":',
        '{"ok":true} trailing explanation',
        '{"ok":true} {"second":true}',
    ],
)
def test_normalize_json_object_rejects_ambiguous_or_invalid_output(raw: str) -> None:
    with pytest.raises(StructuredOutputError):
        normalize_json_object(raw)
