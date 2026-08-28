"""仓库快照、源码索引和引用证据模型。"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field, model_validator

from vibeproof.core.models.common import FileCategory, StrictModel, SymbolKind


class GitSnapshot(StrictModel):
    """扫描时读取到的 Git 分支、提交和工作区状态。"""

    available: bool = False
    branch: str | None = None
    commit: str | None = None
    dirty: bool | None = None
    note: str | None = None


class RepositoryFile(StrictModel):
    """仓库内一个可读取文件的路径、类别和内容哈希。"""

    path: str
    category: FileCategory
    language: str | None = None
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)


class ScanStatistics(StrictModel):
    """扫描读取、忽略和跳过文件的计数。"""

    visited_files: int = Field(default=0, ge=0)
    indexed_files: int = Field(default=0, ge=0)
    ignored_directories: int = Field(default=0, ge=0)
    skipped_sensitive: int = Field(default=0, ge=0)
    skipped_binary: int = Field(default=0, ge=0)
    skipped_too_large: int = Field(default=0, ge=0)
    skipped_unreadable: int = Field(default=0, ge=0)
    skipped_symlinks: int = Field(default=0, ge=0)


class RepositoryManifest(StrictModel):
    """仓库扫描产物；它是后续源码证据共同绑定的不可变快照。"""

    schema_version: str = "1.0"
    repository_name: str
    snapshot_id: str
    scanned_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    git: GitSnapshot = Field(default_factory=GitSnapshot)
    languages: dict[str, int] = Field(default_factory=dict)
    frameworks: list[str] = Field(default_factory=list)
    entrypoints: list[str] = Field(default_factory=list)
    dependency_files: list[str] = Field(default_factory=list)
    test_files: list[str] = Field(default_factory=list)
    documentation_files: list[str] = Field(default_factory=list)
    configuration_files: list[str] = Field(default_factory=list)
    files: list[RepositoryFile] = Field(default_factory=list)
    statistics: ScanStatistics = Field(default_factory=ScanStatistics)
    warnings: list[str] = Field(default_factory=list)


class SourceSymbol(StrictModel):
    """从 AST 中提取的类、函数或方法及其源码范围。"""

    symbol_id: str
    snapshot_id: str
    path: str
    module: str
    qualified_name: str
    kind: SymbolKind
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    signature: str | None = None
    docstring: str | None = None
    decorators: list[str] = Field(default_factory=list)
    parent_name: str | None = None

    @model_validator(mode="after")
    def validate_line_range(self) -> SourceSymbol:
        """确保符号结束行不早于开始行。"""
        if self.end_line < self.start_line:
            raise ValueError("end_line cannot be before start_line")
        return self


class ImportEdge(StrictModel):
    """一个 Python 文件中的静态导入关系。"""

    snapshot_id: str
    source_path: str
    module: str
    imported_name: str | None = None
    alias: str | None = None
    level: int = Field(default=0, ge=0)
    line: int = Field(ge=1)


class SourceChunk(StrictModel):
    """可被检索和引用的带行号源码块。"""

    chunk_id: str
    snapshot_id: str
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content_hash: str = Field(min_length=64, max_length=64)
    content: str
    symbol: str | None = None
    symbol_kind: SymbolKind = SymbolKind.MODULE

    @model_validator(mode="after")
    def validate_line_range(self) -> SourceChunk:
        """确保源码块行号范围有效。"""
        if self.end_line < self.start_line:
            raise ValueError("end_line cannot be before start_line")
        return self


class EvidenceHit(StrictModel):
    """一次检索返回给 Agent 的源码证据及相关度分数。"""

    chunk_id: str
    snapshot_id: str
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    symbol: str | None = None
    symbol_kind: SymbolKind
    score: float = Field(ge=0)
    content_hash: str = Field(min_length=64, max_length=64)
    excerpt: str


class EvidenceReference(StrictModel):
    """不含源码正文的稳定引用，用于分享报告和重新校验。"""

    chunk_id: str
    snapshot_id: str
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    symbol: str | None = None
    symbol_kind: SymbolKind
    content_hash: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_line_range(self) -> EvidenceReference:
        """确保引用的源码行范围有效。"""
        if self.end_line < self.start_line:
            raise ValueError("end_line cannot be before start_line")
        return self


class SourceIndexSummary(StrictModel):
    """持久化索引的规模、快照和数据库位置摘要。"""

    repository_name: str
    snapshot_id: str
    indexed_files: int = Field(ge=0)
    symbol_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    import_count: int = Field(ge=0)
    database_path: str
    warnings: list[str] = Field(default_factory=list)
