"""规范化真实模型常见的 JSON 包装，同时保留严格数据契约校验。

模型有时会把合法 JSON 放入 Markdown 代码块或附加简短说明。本模块只提取第一个完整 JSON 对象，拒绝
缺失对象、数组、多个对象和非空尾随内容；提取结果仍必须通过调用方的 Pydantic 模型校验。
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass

from pydantic import BaseModel


class StructuredOutputError(ValueError):
    """模型文本无法唯一解析为一个 JSON 对象。"""


@dataclass(frozen=True)
class StructuredOutputSpec:
    """由 Pydantic 模型派生的唯一输出契约，供各模型 Provider 转换为原生约束。"""

    name: str
    schema: dict[str, object]

    @classmethod
    def from_model(cls, name: str, model: type[BaseModel]) -> StructuredOutputSpec:
        """生成 OpenAI strict 模式可接受的 schema，并让所有对象字段都显式出现。"""
        if not name or not name.replace("_", "").isalnum():
            raise ValueError("structured output name must contain only letters, numbers, and underscores")
        schema = deepcopy(model.model_json_schema())
        _make_schema_strict(schema)
        return cls(name=name, schema=schema)

    def openai_response_format(self) -> dict[str, object]:
        """转换成 Chat Completions 的严格 ``response_format``。"""
        return {
            "type": "json_schema",
            "json_schema": {"name": self.name, "strict": True, "schema": self.schema},
        }


def normalize_json_object(raw: str) -> str:
    """去掉有限的 Markdown 包装，但拒绝 JSON 前后夹带额外解释。"""
    text = raw.strip()
    if not text:
        raise StructuredOutputError("model output was empty")

    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline < 0 or not text.endswith("```"):
            raise StructuredOutputError("model output contained an incomplete Markdown code fence")
        text = text[first_newline + 1 : -3].strip()

    start = text.find("{")
    if start < 0:
        raise StructuredOutputError("model output did not contain a JSON object")
    prefix = text[:start].strip()
    candidate = text[start:]
    try:
        value, end = json.JSONDecoder().raw_decode(candidate)
    except json.JSONDecodeError as exc:
        raise StructuredOutputError(f"model output contained invalid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise StructuredOutputError("model output JSON must be an object")
    trailing = candidate[end:].strip()
    if trailing == "```" and "```" in prefix:
        trailing = ""
    if trailing:
        raise StructuredOutputError("model output contained non-empty content after the JSON object")
    return json.dumps(value, ensure_ascii=False)


def _make_schema_strict(node: object) -> None:
    """递归满足 strict JSON Schema：对象禁止额外字段，且声明全部属性。"""
    if isinstance(node, list):
        for item in node:
            _make_schema_strict(item)
        return
    if not isinstance(node, dict):
        return
    node.pop("default", None)
    properties = node.get("properties")
    if isinstance(properties, dict):
        node["additionalProperties"] = False
        node["required"] = list(properties)
    for value in node.values():
        _make_schema_strict(value)
