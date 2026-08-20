"""验证仓库静态扫描器的识别能力和读取边界。

测试构造不同文件、框架和 Git 元数据场景，检查快照确定性、入口与依赖识别，以及敏感文件、二进制、
大文件、符号链接和越界数量的跳过规则。
"""

from pathlib import Path

from vibeproof.scanner import RepositoryScanner, ScanPolicy
from vibeproof.schemas import FileCategory


def build_demo_repository(root: Path) -> None:
    (root / "src" / "demo").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / ".venv").mkdir()
    (root / ".vibeproof").mkdir()
    (root / ".git" / "refs" / "heads").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["fastapi>=0.116", "sqlalchemy>=2"]\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text("# Demo repository\n", encoding="utf-8")
    (root / "src" / "demo" / "main.py").write_text(
        "from fastapi import FastAPI\n\napp = FastAPI()\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_main.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (root / ".env").write_text("TOKEN=do-not-index\n", encoding="utf-8")
    (root / ".env.example").write_text("TOKEN=\n", encoding="utf-8")
    (root / ".venv" / "secret.py").write_text("SHOULD_NOT_BE_INDEXED = True\n", encoding="utf-8")
    (root / ".vibeproof" / "index.sqlite3").write_bytes(b"local source index")
    (root / "logo.png").write_bytes(b"\x89PNG\x00binary")
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (root / ".git" / "refs" / "heads" / "main").write_text("a" * 40 + "\n", encoding="utf-8")


def test_scanner_builds_stable_manifest_without_secrets(tmp_path: Path) -> None:
    build_demo_repository(tmp_path)
    scanner = RepositoryScanner()

    first = scanner.scan(tmp_path)
    second = scanner.scan(tmp_path)

    assert first.repository_name == tmp_path.name
    assert first.snapshot_id == second.snapshot_id
    assert first.git.available is True
    assert first.git.branch == "main"
    assert first.git.commit == "a" * 40
    assert first.git.dirty is None
    assert first.languages["Python"] == 2
    assert {"FastAPI", "SQLAlchemy"}.issubset(first.frameworks)
    assert "src/demo/main.py" in first.entrypoints
    assert "tests/test_main.py" not in first.entrypoints
    assert "pyproject.toml" in first.dependency_files
    assert "tests/test_main.py" in first.test_files
    assert "README.md" in first.documentation_files
    assert ".env.example" in first.configuration_files

    indexed_paths = {item.path for item in first.files}
    assert ".env" not in indexed_paths
    assert ".venv/secret.py" not in indexed_paths
    assert ".vibeproof/index.sqlite3" not in indexed_paths
    assert "logo.png" not in indexed_paths
    assert first.statistics.skipped_sensitive == 1
    assert first.statistics.skipped_binary == 1
    assert first.statistics.ignored_directories >= 2


def test_snapshot_changes_when_source_changes(tmp_path: Path) -> None:
    build_demo_repository(tmp_path)
    scanner = RepositoryScanner()
    before = scanner.scan(tmp_path).snapshot_id

    (tmp_path / "src" / "demo" / "main.py").write_text("print('changed')\n", encoding="utf-8")

    after = scanner.scan(tmp_path).snapshot_id
    assert after != before


def test_scanner_enforces_file_limit(tmp_path: Path) -> None:
    for index in range(5):
        (tmp_path / f"module_{index}.py").write_text(f"VALUE = {index}\n", encoding="utf-8")

    manifest = RepositoryScanner(ScanPolicy(max_files=2)).scan(tmp_path)

    assert len(manifest.files) == 2
    assert manifest.statistics.indexed_files == 2
    assert manifest.warnings == ["scan stopped after reaching max_files=2"]


def test_categories_are_typed(tmp_path: Path) -> None:
    build_demo_repository(tmp_path)
    manifest = RepositoryScanner().scan(tmp_path)
    by_path = {item.path: item for item in manifest.files}

    assert by_path["pyproject.toml"].category == FileCategory.DEPENDENCY
    assert by_path["tests/test_main.py"].category == FileCategory.TEST
    assert by_path["README.md"].category == FileCategory.DOCUMENTATION
