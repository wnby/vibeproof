"""集中定义 VibeProof 各阶段共享的严格数据契约。

这里使用 Pydantic 模型和枚举描述仓库清单、源码证据、Agent 动作、架构报告、学习计划、运行结果、
答题提交与学习进度，并通过字段及跨字段校验阻止不完整或互相矛盾的状态流入系统。
"""

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


class TakeoverStatus(StrEnum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SNAPSHOT_CHANGED = "SNAPSHOT_CHANGED"


class TakeoverStage(StrEnum):
    SCAN = "SCAN"
    INDEX = "INDEX"
    ANALYZE = "ANALYZE"
    LEARNING_PLAN = "LEARNING_PLAN"
    RUNTIME_PLAN = "RUNTIME_PLAN"
    RUNTIME_EXECUTION = "RUNTIME_EXECUTION"
    REPORT = "REPORT"


class StageStatus(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class LearningPlanStatus(StrEnum):
    SOURCE_GROUNDED = "SOURCE_GROUNDED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class QuizDifficulty(StrEnum):
    BASIC = "BASIC"
    APPLIED = "APPLIED"
    TRACE = "TRACE"


class AnswerAssessmentStatus(StrEnum):
    ANSWERED = "ANSWERED"
    NEEDS_IMPROVEMENT = "NEEDS_IMPROVEMENT"
    NOT_ASSESSED = "NOT_ASSESSED"
    REJECTED = "REJECTED"


class AnswerReviewStatus(StrEnum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ReviewMode(StrEnum):
    MODEL_ASSESSED = "MODEL_ASSESSED"
    STRUCTURE_ONLY = "STRUCTURE_ONLY"


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


class LearningUnitDraft(StrictModel):
    sequence: int = Field(ge=1, le=10)
    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=600)
    why_it_matters: str = Field(min_length=1, max_length=600)
    exercise: str = Field(min_length=1, max_length=600)
    evidence_ids: list[str] = Field(default_factory=list, max_length=5)


class QuizQuestionDraft(StrictModel):
    question_id: str = Field(min_length=1, max_length=80)
    unit_sequence: int = Field(ge=1, le=10)
    difficulty: QuizDifficulty
    prompt: str = Field(min_length=1, max_length=800)
    evaluation_points: list[str] = Field(default_factory=list, max_length=6)
    evidence_ids: list[str] = Field(default_factory=list, max_length=5)


class LearningPlanDraft(StrictModel):
    summary: str = Field(min_length=1, max_length=2_000)
    units: list[LearningUnitDraft] = Field(default_factory=list, max_length=5)
    questions: list[QuizQuestionDraft] = Field(default_factory=list, max_length=15)


class LearningPlan(StrictModel):
    plan_id: str = Field(default_factory=lambda: f"learning:{uuid4().hex}")
    repository_name: str
    snapshot_id: str
    status: LearningPlanStatus
    provider: str
    model: str
    summary: str
    units: list[LearningUnitDraft] = Field(default_factory=list)
    questions: list[QuizQuestionDraft] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    rejected_items: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_grounded_plan(self) -> LearningPlan:
        if self.status == LearningPlanStatus.SOURCE_GROUNDED and not all(
            (self.units, self.questions, self.evidence)
        ):
            raise ValueError("source-grounded learning plans require units, questions, and evidence")
        return self


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


class RepositorySummary(StrictModel):
    repository_name: str
    snapshot_id: str
    languages: dict[str, int] = Field(default_factory=dict)
    frameworks: list[str] = Field(default_factory=list)
    entrypoints: list[str] = Field(default_factory=list)
    dependency_files: list[str] = Field(default_factory=list)
    test_files: list[str] = Field(default_factory=list)
    scanned_files: int = Field(ge=0)


class TakeoverStep(StrictModel):
    step: int = Field(ge=1)
    stage: TakeoverStage
    status: StageStatus
    summary: str
    duration_ms: int = Field(ge=0)
    error: str | None = None


class TakeoverReport(StrictModel):
    report_id: str = Field(default_factory=lambda: f"takeover:{uuid4().hex}")
    repository_name: str
    snapshot_id: str | None = None
    status: TakeoverStatus
    summary: str
    repository: RepositorySummary | None = None
    source_index: SourceIndexSummary | None = None
    architecture: ArchitectureReport | None = None
    learning_plan: LearningPlan | None = None
    runtime: RuntimeVerificationReport | None = None
    steps: list[TakeoverStep] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_completed_report(self) -> TakeoverReport:
        if self.status == TakeoverStatus.COMPLETED and not all(
            (self.repository, self.source_index, self.architecture, self.learning_plan, self.runtime)
        ):
            raise ValueError("completed takeover reports require every workflow artifact")
        if self.repository is not None and self.snapshot_id != self.repository.snapshot_id:
            raise ValueError("report and repository snapshot IDs must match")
        return self


class AnswerSubmission(StrictModel):
    question_id: str = Field(min_length=1, max_length=80)
    answer: str = Field(default="", max_length=8_000)


class QuizSubmission(StrictModel):
    schema_version: str = "1.0"
    report_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    answers: list[AnswerSubmission] = Field(default_factory=list, max_length=100)
    submitted_at: datetime | None = None

    @model_validator(mode="after")
    def validate_unique_answers(self) -> QuizSubmission:
        question_ids = [item.question_id for item in self.answers]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("quiz submission contains duplicate question IDs")
        return self


class AnswerAssessmentDraft(StrictModel):
    question_id: str = Field(min_length=1, max_length=80)
    score: int | None = Field(default=None, ge=0, le=100)
    feedback: str = Field(min_length=1, max_length=2_000)
    strengths: list[str] = Field(default_factory=list, max_length=6)
    gaps: list[str] = Field(default_factory=list, max_length=6)
    evidence_ids: list[str] = Field(default_factory=list, max_length=5)


class AnswerAssessment(StrictModel):
    question_id: str = Field(min_length=1, max_length=80)
    unit_sequence: int = Field(ge=1, le=10)
    status: AnswerAssessmentStatus
    score: int | None = Field(default=None, ge=0, le=100)
    feedback: str = Field(min_length=1, max_length=2_000)
    strengths: list[str] = Field(default_factory=list, max_length=6)
    gaps: list[str] = Field(default_factory=list, max_length=6)
    evidence_ids: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def validate_score_state(self) -> AnswerAssessment:
        assessed = self.status in {
            AnswerAssessmentStatus.ANSWERED,
            AnswerAssessmentStatus.NEEDS_IMPROVEMENT,
        }
        if assessed and self.score is None:
            raise ValueError("semantically assessed answers require a score")
        if not assessed and self.score is not None:
            raise ValueError("unassessed or rejected answers cannot have a score")
        return self


class LearningProgress(StrictModel):
    total_questions: int = Field(ge=0)
    answered_questions: int = Field(ge=0)
    assessed_questions: int = Field(ge=0)
    passed_questions: int = Field(ge=0)
    needs_improvement: int = Field(ge=0)
    not_assessed: int = Field(ge=0)
    rejected: int = Field(ge=0)
    completion_percent: float = Field(ge=0, le=100)
    mastery_percent: float = Field(ge=0, le=100)
    weak_units: list[int] = Field(default_factory=list)
    recommended_next_units: list[int] = Field(default_factory=list)


class AnswerReviewReport(StrictModel):
    review_id: str = Field(default_factory=lambda: f"answer-review:{uuid4().hex}")
    report_id: str
    plan_id: str
    repository_name: str
    snapshot_id: str
    status: AnswerReviewStatus
    mode: ReviewMode
    provider: str
    model: str
    assessments: list[AnswerAssessment] = Field(default_factory=list)
    progress: LearningProgress
    evidence: list[EvidenceReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
