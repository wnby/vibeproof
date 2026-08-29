"""在模型可读的短证据别名与内部完整 chunk ID 之间做确定性映射。

模型擅长基于证据推理，但不适合逐字符复制长哈希。Agent 提示词只暴露 ``E1``、``E2`` 这类
本次调用内稳定的句柄；进入证据审查前再恢复数据库使用的完整 ID。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

_ALIAS_TOKEN = re.compile(r"(?<![A-Za-z0-9_])E\d+(?![A-Za-z0-9_])")
_ALIAS_SEPARATORS = " `*_[](){}<>.,;:，。；：、/\\|\t\r\n"


@dataclass(frozen=True)
class EvidenceAliases:
    """维护一次 Agent 上下文内的双向证据 ID 映射。"""

    alias_to_chunk_id: dict[str, str]

    @classmethod
    def from_chunk_ids(cls, chunk_ids: Iterable[str]) -> EvidenceAliases:
        """按首次出现顺序生成稳定、去重的 ``E<number>`` 别名。"""
        unique_ids = list(dict.fromkeys(chunk_ids))
        return cls({f"E{index}": chunk_id for index, chunk_id in enumerate(unique_ids, start=1)})

    def alias(self, chunk_id: str) -> str:
        """把内部 ID 转成模型句柄；未知 ID 保持原值以便后续审查拒绝。"""
        return self.chunk_id_to_alias.get(chunk_id, chunk_id)

    def resolve(self, reference: str) -> str:
        """把模型句柄恢复为内部 ID；只容忍句柄外围的展示标点，未知引用仍原样保留。"""
        aliases = _parse_alias_list(reference)
        if len(aliases) != 1:
            return reference
        return self.alias_to_chunk_id.get(aliases[0], reference)

    def aliases(self, chunk_ids: Iterable[str]) -> list[str]:
        """批量转换内部 ID。"""
        return [self.alias(chunk_id) for chunk_id in chunk_ids]

    def resolve_all(self, references: Iterable[str]) -> list[str]:
        """批量恢复模型引用，并拆开仅由安全分隔符连接的多个短句柄。"""
        resolved: list[str] = []
        for reference in references:
            aliases = _parse_alias_list(reference)
            if not aliases:
                resolved.append(reference)
                continue
            resolved.extend(self.alias_to_chunk_id.get(alias, alias) for alias in aliases)
        return resolved

    @property
    def chunk_id_to_alias(self) -> dict[str, str]:
        """返回反向映射，避免调用方各自重建规则。"""
        return {chunk_id: alias for alias, chunk_id in self.alias_to_chunk_id.items()}


def _parse_alias_list(reference: str) -> list[str]:
    """只解析由短别名和展示分隔符组成的字符串，避免从普通文本中宽松提取引用。"""
    aliases = _ALIAS_TOKEN.findall(reference)
    if not aliases:
        return []
    remainder = _ALIAS_TOKEN.sub("", reference)
    return aliases if not remainder.strip(_ALIAS_SEPARATORS) else []
