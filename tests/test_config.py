"""集中配置必须完整映射环境变量，并在入口处完成基础校验。"""

from pathlib import Path

import pytest

from vibeproof.config import ConfigurationError, Settings


def test_settings_loads_application_environment(monkeypatch) -> None:
    monkeypatch.setenv("VIBEPROOF_WORKSPACE_ROOT", "D:/repositories")
    monkeypatch.setenv("VIBEPROOF_DATABASE", "state/evidence.sqlite3")
    monkeypatch.setenv("VIBEPROOF_AI_PROVIDER", "OPENAI-COMPATIBLE")
    monkeypatch.setenv("VIBEPROOF_AI_MODEL", "test-model")
    monkeypatch.setenv("VIBEPROOF_AI_BASE_URL", "https://models.example/v1")
    monkeypatch.setenv("VIBEPROOF_AI_API_KEY", "test-key")
    monkeypatch.setenv("VIBEPROOF_AI_TIMEOUT_SECONDS", "45")

    settings = Settings.from_env()

    assert settings.workspace_root == Path("D:/repositories")
    assert settings.database == Path("state/evidence.sqlite3")
    assert settings.ai_provider == "openai-compatible"
    assert settings.ai_model == "test-model"
    assert settings.ai_base_url == "https://models.example/v1"
    assert settings.ai_api_key == "test-key"
    assert settings.ai_timeout_seconds == 45


def test_settings_rejects_invalid_timeout(monkeypatch) -> None:
    monkeypatch.setenv("VIBEPROOF_AI_TIMEOUT_SECONDS", "later")

    with pytest.raises(ConfigurationError, match="must be a number"):
        Settings.from_env()
