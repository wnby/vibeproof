"""为仓库教学 Agent 选择有限且有代表性的源码证据。

选择器综合架构报告引用、入口文件、测试、框架和依赖信息，在查询次数和证据数量预算内构造学习
上下文，防止把整个仓库无边界地塞入模型提示词。
"""

from __future__ import annotations

from dataclasses import dataclass

from vibeproof.evidence_store import EvidenceStore
from vibeproof.schemas import ArchitectureReport, EvidenceHit, RepositoryManifest


@dataclass(frozen=True)
class LearningEvidencePolicy:
    max_evidence: int = 12
    search_limit: int = 2
    max_queries: int = 8

    def __post_init__(self) -> None:
        if self.max_evidence < 1 or self.max_evidence > 30:
            raise ValueError("max_evidence must be between 1 and 30")
        if self.search_limit < 1 or self.search_limit > 10:
            raise ValueError("search_limit must be between 1 and 10")
        if self.max_queries < 1 or self.max_queries > 20:
            raise ValueError("max_queries must be between 1 and 20")


@dataclass(frozen=True)
class LearningEvidenceSelection:
    evidence: tuple[EvidenceHit, ...]
    queries: tuple[str, ...]


class LearningEvidenceSelector:
    def __init__(self, store: EvidenceStore, policy: LearningEvidencePolicy | None = None):
        self.store = store
        self.policy = policy or LearningEvidencePolicy()

    def select(
        self,
        manifest: RepositoryManifest,
        architecture: ArchitectureReport,
    ) -> LearningEvidenceSelection:
        selected: dict[str, EvidenceHit] = {}
        architecture_ids = [item.chunk_id for item in architecture.evidence]
        for hit in self.store.get_hits(manifest.snapshot_id, architecture_ids):
            selected[hit.chunk_id] = hit
            if len(selected) >= self.policy.max_evidence:
                return LearningEvidenceSelection(tuple(selected.values()), ())

        queries = _candidate_queries(manifest)[: self.policy.max_queries]
        completed_queries: list[str] = []
        for query in queries:
            if len(selected) >= self.policy.max_evidence:
                break
            completed_queries.append(query)
            hits = self.store.search(manifest.snapshot_id, query, limit=self.policy.search_limit)
            for hit in hits:
                selected.setdefault(hit.chunk_id, hit)
                if len(selected) >= self.policy.max_evidence:
                    break
        return LearningEvidenceSelection(tuple(selected.values()), tuple(completed_queries))


def _candidate_queries(manifest: RepositoryManifest) -> list[str]:
    candidates = [
        *manifest.entrypoints[:2],
        *manifest.test_files[:2],
        *manifest.frameworks[:2],
        *manifest.dependency_files[:1],
    ]
    if not candidates:
        candidates = ["main", "test", "service"]
    return list(dict.fromkeys(candidates))
