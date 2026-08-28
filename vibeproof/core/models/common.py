"""跨领域共享的严格模型基类与状态枚举。"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


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


class EvaluationMetricStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INFO = "INFO"


class EvaluationStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
