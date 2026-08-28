"""跨领域共享的严格模型基类与状态枚举。"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """拒绝未知字段的公共 Pydantic 基类，避免模型输出静默污染状态。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class VerificationStatus(StrEnum):
    """证据或结论的可验证程度。"""

    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class EvidenceKind(StrEnum):
    """证据来自仓库清单、源码、运行结果或用户答案。"""

    MANIFEST = "MANIFEST"
    SOURCE = "SOURCE"
    RUNTIME = "RUNTIME"
    USER_ANSWER = "USER_ANSWER"


class FileCategory(StrEnum):
    """扫描器对仓库文件的用途分类。"""

    SOURCE = "SOURCE"
    TEST = "TEST"
    DOCUMENTATION = "DOCUMENTATION"
    DEPENDENCY = "DEPENDENCY"
    CONFIGURATION = "CONFIGURATION"


class SymbolKind(StrEnum):
    """AST 索引可以识别的 Python 符号种类。"""

    MODULE = "MODULE"
    CLASS = "CLASS"
    FUNCTION = "FUNCTION"
    ASYNC_FUNCTION = "ASYNC_FUNCTION"
    METHOD = "METHOD"
    ASYNC_METHOD = "ASYNC_METHOD"


class ClaimType(StrEnum):
    """Analyst 架构结论的主题分类。"""

    ENTRYPOINT = "ENTRYPOINT"
    COMPONENT = "COMPONENT"
    DEPENDENCY = "DEPENDENCY"
    DATA_FLOW = "DATA_FLOW"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    RISK = "RISK"
    OTHER = "OTHER"


class ClaimStatus(StrEnum):
    """引用审查后架构结论的最终状态。"""

    VERIFIED_FACT = "VERIFIED_FACT"
    SOURCE_SUPPORTED = "SOURCE_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    REJECTED = "REJECTED"


class AgentActionType(StrEnum):
    """Analyst 在循环中唯一允许输出的两类动作。"""

    SEARCH_SOURCE = "SEARCH_SOURCE"
    FINAL_ANSWER = "FINAL_ANSWER"


class AgentRunStatus(StrEnum):
    """Analyst 循环结束的原因。"""

    COMPLETED = "COMPLETED"
    MAX_STEPS = "MAX_STEPS"
    INVALID_ACTION = "INVALID_ACTION"
    MODEL_ERROR = "MODEL_ERROR"


class RuntimeCheck(StrEnum):
    """运行验证允许选择的固定命令目录。"""

    PYTEST = "PYTEST"
    PYTEST_COLLECT = "PYTEST_COLLECT"


class InterpreterSource(StrEnum):
    """运行测试所用 Python 解释器的来源。"""

    EXPLICIT = "EXPLICIT"
    REPOSITORY_VENV = "REPOSITORY_VENV"
    CURRENT_PROCESS = "CURRENT_PROCESS"


class RuntimeStatus(StrEnum):
    """运行计划或执行结果状态。"""

    PLANNED = "PLANNED"
    PASSED = "PASSED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    SNAPSHOT_CHANGED = "SNAPSHOT_CHANGED"


class TakeoverStatus(StrEnum):
    """完整仓库接管最终状态。"""

    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SNAPSHOT_CHANGED = "SNAPSHOT_CHANGED"


class TakeoverStage(StrEnum):
    """Takeover 黄金路径中的固定阶段。"""

    SCAN = "SCAN"
    INDEX = "INDEX"
    ANALYZE = "ANALYZE"
    LEARNING_PLAN = "LEARNING_PLAN"
    RUNTIME_PLAN = "RUNTIME_PLAN"
    RUNTIME_EXECUTION = "RUNTIME_EXECUTION"
    REPORT = "REPORT"


class StageStatus(StrEnum):
    """单个 Takeover 阶段是否完成。"""

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class LearningPlanStatus(StrEnum):
    """学习计划的证据完整程度。"""

    SOURCE_GROUNDED = "SOURCE_GROUNDED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class QuizDifficulty(StrEnum):
    """题目从基础识别到调用链追踪的难度。"""

    BASIC = "BASIC"
    APPLIED = "APPLIED"
    TRACE = "TRACE"


class AnswerAssessmentStatus(StrEnum):
    """单道答案的评审状态。"""

    ANSWERED = "ANSWERED"
    NEEDS_IMPROVEMENT = "NEEDS_IMPROVEMENT"
    NOT_ASSESSED = "NOT_ASSESSED"
    REJECTED = "REJECTED"


class AnswerReviewStatus(StrEnum):
    """整份答题提交的评审状态。"""

    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ReviewMode(StrEnum):
    """答案是由真实模型语义评审，还是仅完成 Mock 结构检查。"""

    MODEL_ASSESSED = "MODEL_ASSESSED"
    STRUCTURE_ONLY = "STRUCTURE_ONLY"


class EvaluationMetricStatus(StrEnum):
    """单个 Eval 指标的结果类型。"""

    PASS = "PASS"
    FAIL = "FAIL"
    INFO = "INFO"


class EvaluationStatus(StrEnum):
    """一组确定性质量门槛的最终结果。"""

    PASSED = "PASSED"
    FAILED = "FAILED"
