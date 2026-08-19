import json
import sys
from pathlib import Path

from vibeproof.cli import main


def test_index_and_search_cli_round_trip(tmp_path: Path, capsys) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "main.py").write_text(
        "def repository_entrypoint() -> str:\n    return 'ready'\n",
        encoding="utf-8",
    )
    database = tmp_path / "state" / "index.sqlite3"

    index_exit = main(["index", str(repository), "--database", str(database)])
    index_output = json.loads(capsys.readouterr().out)
    search_exit = main(["search", str(repository), "repository_entrypoint", "--database", str(database), "--json"])
    search_output = json.loads(capsys.readouterr().out)

    assert index_exit == 0
    assert index_output["indexed_files"] == 1
    assert search_exit == 0
    assert search_output[0]["symbol"] == "repository_entrypoint"
    assert search_output[0]["path"] == "main.py"


def test_search_cli_explains_missing_index(tmp_path: Path, capsys) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "main.py").write_text("VALUE = 1\n", encoding="utf-8")

    exit_code = main(["search", str(repository), "VALUE", "--database", str(tmp_path / "missing.sqlite3")])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "run `vibeproof index` first" in captured.err


def test_analyze_cli_writes_mock_markdown_report(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "main.py").write_text(
        "def repository_entrypoint() -> str:\n    return 'ready'\n",
        encoding="utf-8",
    )
    database = tmp_path / "state" / "index.sqlite3"
    report_path = tmp_path / "reports" / "architecture.md"
    assert main(["index", str(repository), "--database", str(database)]) == 0

    exit_code = main(
        [
            "analyze",
            str(repository),
            "--database",
            str(database),
            "--provider",
            "mock",
            "--format",
            "markdown",
            "--output",
            str(report_path),
        ]
    )

    assert exit_code == 0
    rendered = report_path.read_text(encoding="utf-8")
    assert "# Architecture report" in rendered
    assert "repository_entrypoint" in rendered
    assert "SOURCE_SUPPORTED" in rendered


def test_verify_cli_is_plan_only_by_default(tmp_path: Path, capsys) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    exit_code = main(["verify", str(repository), "--check", "pytest"])
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert report["status"] == "PLANNED"
    assert report["executed"] is False


def test_verify_cli_executes_only_with_execute_flag(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    report_path = tmp_path / "runtime.md"

    exit_code = main(
        [
            "verify",
            str(repository),
            "--execute",
            "--python",
            sys.executable,
            "--format",
            "markdown",
            "--output",
            str(report_path),
        ]
    )

    assert exit_code == 0
    rendered = report_path.read_text(encoding="utf-8")
    assert "# Runtime verification" in rendered
    assert "Command status: `PASSED`" in rendered


def test_takeover_cli_runs_unified_plan_only_workflow(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "main.py").write_text(
        "def repository_entrypoint() -> str:\n    return 'ready'\n",
        encoding="utf-8",
    )
    database = tmp_path / "state" / "index.sqlite3"
    report_path = tmp_path / "reports" / "takeover.md"

    exit_code = main(
        [
            "takeover",
            str(repository),
            "--database",
            str(database),
            "--provider",
            "mock",
            "--format",
            "markdown",
            "--output",
            str(report_path),
        ]
    )

    assert exit_code == 0
    rendered = report_path.read_text(encoding="utf-8")
    assert "# Repository takeover report" in rendered
    assert "Status: `COMPLETED`" in rendered
    assert "Executed: `false`" in rendered
    assert "## Recommended learning path" in rendered
    assert "## Source-grounded quiz" in rendered
    assert "RUNTIME_PLAN" in rendered
