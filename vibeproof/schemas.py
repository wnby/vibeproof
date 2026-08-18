from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class VerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class EvidenceKind(StrEnum):
    MANIFEST = "MANIFEST"
    SOURCE = "SOURCE"
    RUNTIME = "RUNTIME"
    USER_ANSWER = "USER_ANSWER"


class FileCategory(StrEnum):
    SOURCE = "SOURCE"
    TEST = "TEST"
    DOCUMENTATION = "DOCUMENTATION"
    DEPENDENCY = "DEPENDENCY"
    CONFIGURATION = "CONFIGURATION"


class SymbolKind(StrEnum):
    MODULE = "MODULE"
    CLASS = "CLASS"
    FUNCTION = "FUNCTION"
    ASYNC_FUNCTION = "ASYNC_FUNCTION"
    METHOD = "METHOD"
    ASYNC_METHOD = "ASYNC_METHOD"


class GitSnapshot(StrictModel):
    available: bool = False
    branch: str | None = None
    commit: str | None = None
    dirty: bool | None = None
    note: str | None = None


class RepositoryFile(StrictModel):
    path: str
    category: FileCategory
    language: str | None = None
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)


class ScanStatistics(StrictModel):
    visited_files: int = Field(default=0, ge=0)
    indexed_files: int = Field(default=0, ge=0)
    ignored_directories: int = Field(default=0, ge=0)
    skipped_sensitive: int = Field(default=0, ge=0)
    skipped_binary: int = Field(default=0, ge=0)
    skipped_too_large: int = Field(default=0, ge=0)
    skipped_unreadable: int = Field(default=0, ge=0)
    skipped_symlinks: int = Field(default=0, ge=0)


class RepositoryManifest(StrictModel):
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
        if self.end_line < self.start_line:
            raise ValueError("end_line cannot be before start_line")
        return self


class ImportEdge(StrictModel):
    snapshot_id: str
    source_path: str
    module: str
    imported_name: str | None = None
    alias: str | None = None
    level: int = Field(default=0, ge=0)
    line: int = Field(ge=1)


class SourceChunk(StrictModel):
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
        if self.end_line < self.start_line:
            raise ValueError("end_line cannot be before start_line")
        return self


class EvidenceHit(StrictModel):
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


class SourceIndexSummary(StrictModel):
    repository_name: str
    snapshot_id: str
    indexed_files: int = Field(ge=0)
    symbol_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    import_count: int = Field(ge=0)
    database_path: str
    warnings: list[str] = Field(default_factory=list)


class Evidence(StrictModel):
    evidence_id: str = Field(default_factory=lambda: f"evidence:{uuid4().hex}")
    kind: EvidenceKind
    status: VerificationStatus
    claim: str = Field(min_length=1)
    source_path: str | None = None
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    command: list[str] | None = None
    exit_code: int | None = None
    output_excerpt: str | None = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_evidence_location(self) -> Evidence:
        if self.kind == EvidenceKind.SOURCE and not self.source_path:
            raise ValueError("source evidence requires source_path")
        if (self.start_line is not None or self.end_line is not None) and not self.source_path:
            raise ValueError("line evidence requires source_path")
        if self.start_line is not None and self.end_line is not None and self.end_line < self.start_line:
            raise ValueError("end_line cannot be before start_line")
        if self.kind == EvidenceKind.RUNTIME and not self.command:
            raise ValueError("runtime evidence requires a tokenized command")
        return self


class TakeoverReport(StrictModel):
    report_id: str = Field(default_factory=lambda: f"report:{uuid4().hex}")
    repository_name: str
    snapshot_id: str
    status: VerificationStatus
    summary: str
    verified_claims: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
