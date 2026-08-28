"""VibeProof 的集中配置入口。

所有环境变量名称和运行默认值都定义在这里。业务模块接收 ``Settings`` 或显式参数，
不再自行读取环境变量，因此查看本文件即可知道项目有哪些外部配置。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATABASE = Path(".vibeproof/index.sqlite3")
DEFAULT_AI_PROVIDER = "mock"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 180.0
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 120.0
MODEL_MAX_ATTEMPTS = 2
MODEL_RETRY_DELAY_SECONDS = 0.5
VIBEPROOF_USER_AGENT = "VibeProof/0.1 (+https://github.com/wnby/vibeproof)"

MODEL_PROVIDERS = ("mock", "openai-compatible", "ollama")
MODEL_TASKS = ("analyst", "tutor", "review")


class ConfigurationError(ValueError):
    """配置值缺失或格式不正确。"""


@dataclass(frozen=True, slots=True)
class Settings:
    """从环境变量读取的一份不可变应用配置快照。"""

    workspace_root: Path | None
    database: Path
    ai_provider: str
    ai_model: str
    ai_base_url: str
    ai_api_key: str | None
    ai_timeout_seconds: float | None

    @classmethod
    def from_env(cls) -> Settings:
        workspace = os.getenv("VIBEPROOF_WORKSPACE_ROOT", "").strip()
        timeout = _optional_positive_float(
            os.getenv("VIBEPROOF_AI_TIMEOUT_SECONDS", "").strip(),
            name="VIBEPROOF_AI_TIMEOUT_SECONDS",
        )
        return cls(
            workspace_root=Path(workspace).expanduser() if workspace else None,
            database=Path(os.getenv("VIBEPROOF_DATABASE", str(DEFAULT_DATABASE))).expanduser(),
            ai_provider=os.getenv("VIBEPROOF_AI_PROVIDER", DEFAULT_AI_PROVIDER).strip().lower(),
            ai_model=os.getenv("VIBEPROOF_AI_MODEL", "").strip(),
            ai_base_url=os.getenv("VIBEPROOF_AI_BASE_URL", "").strip(),
            ai_api_key=os.getenv("VIBEPROOF_AI_API_KEY") or None,
            ai_timeout_seconds=timeout,
        )


def _optional_positive_float(value: str, *, name: str) -> float | None:
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number") from exc
    if parsed <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return parsed
