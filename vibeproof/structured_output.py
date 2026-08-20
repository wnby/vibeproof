"""规范化真实模型常见的 JSON 包装，同时保留严格数据契约校验。

模型有时会把合法 JSON 放入 Markdown 代码块或附加简短说明。本模块只提取第一个完整 JSON 对象，拒绝
缺失对象、数组、多个对象和非空尾随内容；提取结果仍必须通过调用方的 Pydantic 模型校验。
"""

from __future__ import annotations

import json


class StructuredOutputError(ValueError):
    pass


def normalize_json_object(raw: str) -> str:
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
