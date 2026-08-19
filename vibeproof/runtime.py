from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from vibeproof.scanner import RepositoryScanner, ScanPolicy
from vibeproof.schemas import (
    CommandPlan,
    InterpreterSource,
    RuntimeCheck,
    RuntimeEvidence,
    RuntimeStatus,
    RuntimeVerificationReport,
)

CHECK_ARGUMENTS: dict[RuntimeCheck, tuple[str, ...]] = {
    RuntimeCheck.PYTEST: ("-m", "pytest", "-q"),
    RuntimeCheck.PYTEST_COLLECT: ("-m", "pytest", "--collect-only", "-q"),
}
SECRET_ENV_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "CREDENTIAL")
AUTH_ENV_NAMES = frozenset({"AUTH", "AUTHORIZATION", "AUTHENTICATION"})


@dataclass(frozen=True)
class RuntimePolicy:
    timeout_seconds: float = 120
    output_limit_chars: int = 20_000
    scan_policy: ScanPolicy = ScanPolicy()

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.output_limit_chars <= 0:
            raise ValueError("output_limit_chars must be positive")


@dataclass(frozen=True)
class _Interpreter:
    executable: Path
    source: InterpreterSource
    display_name: str


class RuntimeVerifier:
    """Plan and run a small catalog of Python checks with auditable evidence."""

    def __init__(self, policy: RuntimePolicy | None = None):
        self.policy = policy or RuntimePolicy()
        self.scanner = RepositoryScanner(self.policy.scan_policy)

    def verify(
        self,
        root: str | Path,
        *,
        check: RuntimeCheck = RuntimeCheck.PYTEST,
        execute: bool = False,
        python_executable: str | Path | None = None,
    ) -> RuntimeVerificationReport:
        repository_root = self._resolve_root(root)
        manifest = self.scanner.scan(repository_root)
        interpreter = self._resolve_interpreter(repository_root, python_executable)
        plan = CommandPlan(
            repository_name=manifest.repository_name,
            snapshot_id=manifest.snapshot_id,
            check=check,
            command=[interpreter.display_name, *CHECK_ARGUMENTS[check]],
            interpreter_source=interpreter.source,
            timeout_seconds=self.policy.timeout_seconds,
            output_limit_chars=self.policy.output_limit_chars,
        )
        if not execute:
            return RuntimeVerificationReport(
                repository_name=manifest.repository_name,
                before_snapshot_id=manifest.snapshot_id,
                status=RuntimeStatus.PLANNED,
                executed=False,
                plan=plan,
                warnings=["Plan only: pass --execute to run repository code."],
            )

        evidence = self._execute(repository_root, plan, interpreter.executable)
        warnings: list[str] = []
        after_snapshot_id: str | None = None
        repository_changed = False
        try:
            after_snapshot_id = self.scanner.scan(repository_root).snapshot_id
            repository_changed = after_snapshot_id != manifest.snapshot_id
        except OSError as exc:
            warnings.append(f"Post-execution snapshot could not be read: {exc}")

        status = RuntimeStatus.SNAPSHOT_CHANGED if repository_changed else evidence.status
        if repository_changed:
            warnings.append("Repository snapshot changed while the check was running; changes were not reverted.")
        return RuntimeVerificationReport(
            repository_name=manifest.repository_name,
            before_snapshot_id=manifest.snapshot_id,
            after_snapshot_id=after_snapshot_id,
            status=status,
            executed=True,
            repository_changed=repository_changed,
            plan=plan,
            evidence=evidence,
            warnings=warnings,
        )

    @staticmethod
    def _resolve_root(root: str | Path) -> Path:
        repository_root = Path(root).expanduser().resolve(strict=True)
        if not repository_root.is_dir():
            raise NotADirectoryError(f"repository root is not a directory: {repository_root}")
        return repository_root

    @staticmethod
    def _resolve_interpreter(root: Path, explicit: str | Path | None) -> _Interpreter:
        if explicit is not None:
            executable = Path(os.path.abspath(Path(explicit).expanduser()))
            if not executable.exists():
                raise FileNotFoundError(f"Python executable does not exist: {executable}")
            if not executable.is_file():
                raise ValueError(f"Python executable is not a file: {executable}")
            return _Interpreter(executable, InterpreterSource.EXPLICIT, str(executable))

        relative_candidates = (
            Path(".venv/Scripts/python.exe"),
            Path(".venv/bin/python"),
        )
        for relative in relative_candidates:
            executable = root / relative
            if executable.is_file():
                return _Interpreter(executable, InterpreterSource.REPOSITORY_VENV, relative.as_posix())

        # Keep the venv entry path: on POSIX it is commonly a symlink, and
        # resolving it would discard the virtual environment's site-packages.
        executable = Path(os.path.abspath(sys.executable))
        return _Interpreter(executable, InterpreterSource.CURRENT_PROCESS, str(executable))

    def _execute(self, root: Path, plan: CommandPlan, executable: Path) -> RuntimeEvidence:
        actual_command = [str(executable), *CHECK_ARGUMENTS[plan.check]]
        environment, scrubbed_count = _scrub_environment(os.environ)
        started_at = datetime.now(UTC)
        started = monotonic()
        exit_code: int | None = None
        stdout = ""
        stderr = ""
        error: str | None = None
        status: RuntimeStatus
        try:
            completed = subprocess.run(
                actual_command,
                cwd=root,
                env=environment,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=plan.timeout_seconds,
                check=False,
            )
            exit_code = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
            status = RuntimeStatus.PASSED if exit_code == 0 else RuntimeStatus.FAILED
        except subprocess.TimeoutExpired as exc:
            stdout = _to_text(exc.stdout)
            stderr = _to_text(exc.stderr)
            error = f"Command exceeded timeout of {plan.timeout_seconds:g} seconds"
            status = RuntimeStatus.TIMED_OUT
        except OSError as exc:
            error = f"Command could not be started: {exc}"
            status = RuntimeStatus.EXECUTION_ERROR

        stdout, stderr, truncated = _bound_output(stdout, stderr, plan.output_limit_chars)
        finished_at = datetime.now(UTC)
        duration_ms = max(0, round((monotonic() - started) * 1_000))
        return RuntimeEvidence(
            plan_id=plan.plan_id,
            check=plan.check,
            status=status,
            command=plan.command,
            exit_code=exit_code,
            stdout_excerpt=stdout,
            stderr_excerpt=stderr,
            output_truncated=truncated,
            duration_ms=duration_ms,
            scrubbed_environment_variables=scrubbed_count,
            error=error,
            started_at=started_at,
            finished_at=finished_at,
        )


def _scrub_environment(environment: os._Environ[str] | dict[str, str]) -> tuple[dict[str, str], int]:
    scrubbed = {
        name: value
        for name, value in environment.items()
        if not _is_sensitive_environment_name(name)
    }
    return scrubbed, len(environment) - len(scrubbed)


def _is_sensitive_environment_name(name: str) -> bool:
    normalized = name.upper().replace("-", "_")
    parts = set(normalized.split("_"))
    return any(marker in normalized for marker in SECRET_ENV_MARKERS) or bool(parts & AUTH_ENV_NAMES)


def _to_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _bound_output(stdout: str, stderr: str, limit: int) -> tuple[str, str, bool]:
    if len(stdout) + len(stderr) <= limit:
        return stdout, stderr, False

    stdout_budget = min(len(stdout), limit // 2)
    stderr_budget = min(len(stderr), limit - stdout_budget)
    remaining = limit - stdout_budget - stderr_budget
    if remaining and stdout_budget < len(stdout):
        added = min(remaining, len(stdout) - stdout_budget)
        stdout_budget += added
        remaining -= added
    if remaining and stderr_budget < len(stderr):
        stderr_budget += min(remaining, len(stderr) - stderr_budget)
    return _truncate(stdout, stdout_budget), _truncate(stderr, stderr_budget), True


def _truncate(value: str, budget: int) -> str:
    if len(value) <= budget:
        return value
    removed = len(value) - budget
    marker = f"\n...[truncated {removed} chars]"
    if len(marker) >= budget:
        return marker[:budget]
    return value[: budget - len(marker)] + marker
