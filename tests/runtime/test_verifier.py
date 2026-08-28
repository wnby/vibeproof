"""验证计划优先运行器的命令边界和证据记录。

测试覆盖固定 pytest 目录、解释器选择、显式执行、失败、超时、输出截断、环境变量清理及执行后快照
变化，确保目标代码不会在未授权时运行。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from vibeproof.core.models import InterpreterSource, RuntimeCheck, RuntimeStatus
from vibeproof.runtime.verifier import RuntimePolicy, RuntimeVerifier, _bound_output, _scrub_environment


def _repository(tmp_path: Path, test_body: str) -> Path:
    repository = tmp_path / "repository"
    tests = repository / "tests"
    tests.mkdir(parents=True)
    (repository / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tests / "test_sample.py").write_text(test_body, encoding="utf-8")
    return repository


def test_default_mode_only_creates_a_plan(tmp_path: Path) -> None:
    repository = _repository(tmp_path, "def test_ok():\n    assert True\n")

    report = RuntimeVerifier().verify(repository)

    assert report.status == RuntimeStatus.PLANNED
    assert report.executed is False
    assert report.evidence is None
    assert report.plan.command[1:] == ["-m", "pytest", "-q"]


def test_pytest_check_records_passing_runtime_evidence(tmp_path: Path) -> None:
    repository = _repository(tmp_path, "def test_ok():\n    assert True\n")

    report = RuntimeVerifier().verify(repository, execute=True, python_executable=sys.executable)

    assert report.status == RuntimeStatus.PASSED
    assert report.executed is True
    assert report.evidence is not None
    assert report.evidence.status == RuntimeStatus.PASSED
    assert report.evidence.exit_code == 0
    assert "1 passed" in report.evidence.stdout_excerpt
    assert report.before_snapshot_id == report.after_snapshot_id


def test_pytest_check_records_failure_without_raising(tmp_path: Path) -> None:
    repository = _repository(tmp_path, "def test_nope():\n    assert False\n")

    report = RuntimeVerifier().verify(repository, execute=True, python_executable=sys.executable)

    assert report.status == RuntimeStatus.FAILED
    assert report.evidence is not None
    assert report.evidence.exit_code == 1
    assert "1 failed" in report.evidence.stdout_excerpt


def test_collect_check_uses_fixed_collect_only_arguments(tmp_path: Path) -> None:
    repository = _repository(tmp_path, "def test_ok():\n    assert True\n")

    report = RuntimeVerifier().verify(
        repository,
        check=RuntimeCheck.PYTEST_COLLECT,
        python_executable=sys.executable,
    )

    assert report.plan.command[1:] == ["-m", "pytest", "--collect-only", "-q"]
    assert report.plan.check == RuntimeCheck.PYTEST_COLLECT


def test_timeout_is_runtime_evidence(tmp_path: Path) -> None:
    repository = _repository(
        tmp_path,
        "import time\n\ndef test_slow():\n    time.sleep(2)\n",
    )
    verifier = RuntimeVerifier(RuntimePolicy(timeout_seconds=0.1))

    report = verifier.verify(repository, execute=True, python_executable=sys.executable)

    assert report.status == RuntimeStatus.TIMED_OUT
    assert report.evidence is not None
    assert report.evidence.exit_code is None
    assert "exceeded timeout" in (report.evidence.error or "")


def test_repository_change_is_reported_and_not_reverted(tmp_path: Path) -> None:
    repository = _repository(
        tmp_path,
        "from pathlib import Path\n\ndef test_write():\n    Path('runtime-created.txt').write_text('evidence')\n",
    )

    report = RuntimeVerifier().verify(repository, execute=True, python_executable=sys.executable)

    assert report.status == RuntimeStatus.SNAPSHOT_CHANGED
    assert report.repository_changed is True
    assert report.evidence is not None
    assert report.evidence.status == RuntimeStatus.PASSED
    assert (repository / "runtime-created.txt").read_text() == "evidence"


def test_interpreter_selection_prefers_explicit_then_repository_venv(tmp_path: Path) -> None:
    repository = _repository(tmp_path, "def test_ok():\n    assert True\n")
    explicit = RuntimeVerifier().verify(repository, python_executable=sys.executable)
    assert explicit.plan.interpreter_source == InterpreterSource.EXPLICIT

    venv_python = repository / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
    venv_python.parent.mkdir(parents=True)
    venv_python.write_bytes(b"")
    discovered = RuntimeVerifier().verify(repository)

    assert discovered.plan.interpreter_source == InterpreterSource.REPOSITORY_VENV
    assert discovered.plan.command[0].startswith(".venv/")


def test_secret_looking_environment_names_are_removed() -> None:
    cleaned, removed = _scrub_environment(
        {
            "PATH": "safe",
            "OPENAI_API_KEY": "hidden",
            "ACCESS_TOKEN": "hidden",
            "REQUEST_AUTH": "hidden",
            "AUTHOR": "safe",
        }
    )

    assert cleaned == {"PATH": "safe", "AUTHOR": "safe"}
    assert removed == 3


def test_combined_output_is_bounded() -> None:
    stdout, stderr, truncated = _bound_output("a" * 100, "b" * 100, 80)

    assert truncated is True
    assert len(stdout) + len(stderr) <= 80
    assert "truncated" in stdout
    assert "truncated" in stderr


@pytest.mark.parametrize("timeout,output_limit", [(0, 10), (1, 0)])
def test_runtime_policy_rejects_non_positive_bounds(timeout: int, output_limit: int) -> None:
    with pytest.raises(ValueError):
        RuntimePolicy(timeout_seconds=timeout, output_limit_chars=output_limit)
