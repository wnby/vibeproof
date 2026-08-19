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


class ClaimType(StrEnum):
    ENTRYPOINT = "ENTRYPOINT"
    COMPONENT = "COMPONENT"
    DEPENDENCY = "DEPENDENCY"
    DATA_FLOW = "DATA_FLOW"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    RISK = "RISK"
    OTHER = "OTHER"


class ClaimStatus(StrEnum):
    VERIFIED_FACT = "VERIFIED_FACT"
    SOURCE_SUPPORTED = "SOURCE_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    REJECTED = "REJECTED"


class AgentActionType(StrEnum):
    SEARCH_SOURCE = "SEARCH_SOURCE"
    FINAL_ANSWER = "FINAL_ANSWER"


class AgentRunStatus(StrEnum):
    COMPLETED = "COMPLETED"
    MAX_STEPS = "MAX_STEPS"
    INVALID_ACTION = "INVALID_ACTION"
    MODEL_ERROR = "MODEL_ERROR"


class RuntimeCheck(StrEnum):
    PYTEST = "PYTEST"
    PYTEST_COLLECT = "PYTEST_COLLECT"


class InterpreterSource(StrEnum):
    EXPLICIT = "EXPLICIT"
    REPOSITORY_VENV = "REPOSITORY_VENV"
    CURRENT_PROCESS = "CURRENT_PROCESS"


class RuntimeStatus(StrEnum):
    PLANNED = "PLANNED"
    PASSED = "PASSED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    SNAPSHOT_CHANGED = "SNAPSHOT_CHANGED"


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


class EvidenceReference(StrictModel):
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
        if self.end_line < self.start_line:
            raise ValueError("end_line cannot be before start_line")
        return self


class SourceIndexSummary(StrictModel):
    repository_name: str
    snapshot_id: str
    indexed_files: int = Field(ge=0)
    symbol_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    import_count: int = Field(ge=0)
    database_path: str
    warnings: list[str] = Field(default_factory=list)


class ClaimDraft(StrictModel):
    claim: str = Field(min_length=1, max_length=1_000)
    claim_type: ClaimType = ClaimType.OTHER
    evidence_ids: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(default=0.5, ge=0, le=1)


class AnalysisClaim(ClaimDraft):
    status: ClaimStatus
    rejection_reason: str | None = None


class AgentAction(StrictModel):
    action: AgentActionType
    query: str | None = Field(default=None, max_length=200)
    summary: str | None = Field(default=None, max_length=4_000)
    claims: list[ClaimDraft] = Field(default_factory=list, max_length=30)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_action_payload(self) -> AgentAction:
        if self.action == AgentActionType.SEARCH_SOURCE:
            if not self.query or not self.query.strip():
                raise ValueError("SEARCH_SOURCE requires a non-empty query")
            if self.claims or self.summary or self.unresolved_questions:
                raise ValueError("SEARCH_SOURCE may only contain action and query")
        if self.action == AgentActionType.FINAL_ANSWER:
            if self.query is not None:
                raise ValueError("FINAL_ANSWER cannot contain a query")
            if not self.summary or not self.summary.strip():
                raise ValueError("FINAL_ANSWER requires a summary")
        return self


class AgentTraceStep(StrictModel):
    step: int = Field(ge=1)
    action: str
    query: str | None = None
    returned_evidence_ids: list[str] = Field(default_factory=list)
    message: str | None = None
    error: str | None = None


class ArchitectureReport(StrictModel):
    report_id: str = Field(default_factory=lambda: f"architecture:{uuid4().hex}")
    repository_name: str
    snapshot_id: str
    run_status: AgentRunStatus
    verification_status: VerificationStatus
    provider: str
    model: str
    summary: str
    claims: list[AnalysisClaim] = Field(default_factory=list)
    rejected_claims: list[AnalysisClaim] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    trace: list[AgentTraceStep] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CommandPlan(StrictModel):
    plan_id: str = Field(default_factory=lambda: f"command-plan:{uuid4().hex}")
    repository_name: str
    snapshot_id: str
    check: RuntimeCheck
    command: list[str] = Field(min_length=3)
    interpreter_source: InterpreterSource
    working_directory: str = "."
    timeout_seconds: float = Field(gt=0)
    output_limit_chars: int = Field(gt=0)
    executes_repository_code: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_catalog_command(self) -> CommandPlan:
        expected_arguments = {
            RuntimeCheck.PYTEST: ["-m", "pytest", "-q"],
            RuntimeCheck.PYTEST_COLLECT: ["-m", "pytest", "--collect-only", "-q"],
        }
        if self.command[1:] != expected_arguments[self.check]:
            raise ValueError("command arguments must match the fixed runtime check catalog")
        return self


class RuntimeEvidence(StrictModel):
    evidence_id: str = Field(default_factory=lambda: f"runtime:{uuid4().hex}")
    plan_id: str
    check: RuntimeCheck
    status: RuntimeStatus
    command: list[str] = Field(min_length=3)
    exit_code: int | None = None
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    output_truncated: bool = False
    duration_ms: int = Field(ge=0)
    scrubbed_environment_variables: int = Field(default=0, ge=0)
    error: str | None = None
    started_at: datetime
    finished_at: datetime

    @model_validator(mode="after")
    def validate_runtime_status(self) -> RuntimeEvidence:
        if self.status in {RuntimeStatus.PLANNED, RuntimeStatus.SNAPSHOT_CHANGED}:
            raise ValueError("runtime evidence requires a command execution status")
        return self


class RuntimeVerificationReport(StrictModel):
    report_id: str = Field(default_factory=lambda: f"runtime-report:{uuid4().hex}")
    repository_name: str
    before_snapshot_id: str
    after_snapshot_id: str | None = None
    status: RuntimeStatus
    executed: bool
    repository_changed: bool = False
    plan: CommandPlan
    evidence: RuntimeEvidence | None = None
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_execution_state(self) -> RuntimeVerificationReport:
        if self.executed and self.evidence is None:
            raise ValueError("executed runtime reports require evidence")
        if not self.executed and self.status != RuntimeStatus.PLANNED:
            raise ValueError("unexecuted runtime reports must be PLANNED")
        if self.repository_changed and self.status != RuntimeStatus.SNAPSHOT_CHANGED:
            raise ValueError("changed repositories must use SNAPSHOT_CHANGED status")
        return self


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
