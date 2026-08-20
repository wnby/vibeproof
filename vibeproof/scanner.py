"""对本地仓库进行确定性、非执行式静态扫描。

扫描器识别语言、框架、入口、依赖、测试和配置文件，计算文件及仓库快照哈希，同时跳过敏感文件、
二进制、大文件和符号链接；整个过程不会导入模块或运行 Git 命令。
"""

from __future__ import annotations

import hashlib
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from vibeproof.schemas import (
    FileCategory,
    GitSnapshot,
    RepositoryFile,
    RepositoryManifest,
    ScanStatistics,
)

IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".codecounter",
        ".idea",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        ".vibeproof",
        ".vscodecounter",
        "__pycache__",
        "build",
        "data",
        "dist",
        "htmlcov",
        "node_modules",
        "target",
        "venv",
    }
)

SENSITIVE_FILENAMES = frozenset(
    {
        ".env",
        ".netrc",
        ".npmrc",
        ".pypirc",
        "credentials.json",
        "id_dsa",
        "id_ed25519",
        "id_rsa",
        "pip.conf",
        "secrets.json",
    }
)
SENSITIVE_SUFFIXES = frozenset({".key", ".p12", ".pfx", ".pem"})
BINARY_SUFFIXES = frozenset(
    {
        ".7z",
        ".a",
        ".avi",
        ".bin",
        ".bmp",
        ".class",
        ".dll",
        ".doc",
        ".docx",
        ".exe",
        ".gif",
        ".gz",
        ".ico",
        ".jar",
        ".jpeg",
        ".jpg",
        ".mov",
        ".mp3",
        ".mp4",
        ".o",
        ".pdf",
        ".png",
        ".pyc",
        ".so",
        ".tar",
        ".wav",
        ".webp",
        ".woff",
        ".woff2",
        ".xls",
        ".xlsx",
        ".zip",
    }
)

DEPENDENCY_FILENAMES = frozenset(
    {
        "environment.yml",
        "package-lock.json",
        "package.json",
        "pipfile",
        "pipfile.lock",
        "poetry.lock",
        "pyproject.toml",
        "requirements.txt",
        "uv.lock",
    }
)
ENTRYPOINT_FILENAMES = frozenset({"__main__.py", "app.py", "asgi.py", "cli.py", "main.py", "manage.py", "wsgi.py"})
CONFIG_FILENAMES = frozenset(
    {
        ".dockerignore",
        ".editorconfig",
        ".env.example",
        ".gitignore",
        "docker-compose.yml",
        "docker-compose.yaml",
        "dockerfile",
        "makefile",
    }
)

LANGUAGES_BY_SUFFIX = {
    ".c": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".css": "CSS",
    ".go": "Go",
    ".h": "C/C++ Header",
    ".html": "HTML",
    ".java": "Java",
    ".js": "JavaScript",
    ".json": "JSON",
    ".jsx": "JavaScript JSX",
    ".kt": "Kotlin",
    ".md": "Markdown",
    ".ps1": "PowerShell",
    ".py": "Python",
    ".rb": "Ruby",
    ".rs": "Rust",
    ".sh": "Shell",
    ".sql": "SQL",
    ".toml": "TOML",
    ".ts": "TypeScript",
    ".tsx": "TypeScript JSX",
    ".xml": "XML",
    ".yaml": "YAML",
    ".yml": "YAML",
}

FRAMEWORK_MARKERS = {
    "Celery": ("from celery", "import celery", "celery>="),
    "ChromaDB": ("import chromadb", "chromadb>="),
    "Django": ("from django", "import django", "django>="),
    "FastAPI": ("from fastapi", "import fastapi", "fastapi>="),
    "Flask": ("from flask", "import flask", "flask>="),
    "Pydantic": ("from pydantic", "import pydantic", "pydantic>="),
    "Pytest": ("import pytest", "from pytest", "pytest>="),
    "Redis": ("import redis", "from redis", "redis>="),
    "SQLAlchemy": ("from sqlalchemy", "import sqlalchemy", "sqlalchemy>="),
    "Typer": ("from typer", "import typer", "typer>="),
}


@dataclass(frozen=True)
class ScanPolicy:
    max_files: int = 5_000
    max_file_size_bytes: int = 1_000_000

    def __post_init__(self) -> None:
        if self.max_files < 1:
            raise ValueError("max_files must be positive")
        if self.max_file_size_bytes < 1:
            raise ValueError("max_file_size_bytes must be positive")


class RepositoryScanner:
    def __init__(self, policy: ScanPolicy | None = None):
        self.policy = policy or ScanPolicy()

    def scan(self, root: str | Path) -> RepositoryManifest:
        repository_root = Path(root).expanduser().resolve(strict=True)
        if not repository_root.is_dir():
            raise NotADirectoryError(f"repository root is not a directory: {repository_root}")

        records: list[RepositoryFile] = []
        language_counts: Counter[str] = Counter()
        frameworks: set[str] = set()
        entrypoints: set[str] = set()
        dependency_files: set[str] = set()
        test_files: set[str] = set()
        documentation_files: set[str] = set()
        configuration_files: set[str] = set()
        warnings: list[str] = []
        stats = {
            "visited_files": 0,
            "indexed_files": 0,
            "ignored_directories": 0,
            "skipped_sensitive": 0,
            "skipped_binary": 0,
            "skipped_too_large": 0,
            "skipped_unreadable": 0,
            "skipped_symlinks": 0,
        }
        truncated = False

        for current, directory_names, file_names in os.walk(repository_root, topdown=True, followlinks=False):
            current_path = Path(current)
            kept_directories = []
            for directory_name in sorted(directory_names):
                directory_path = current_path / directory_name
                if directory_name.lower() in IGNORED_DIRECTORIES or directory_path.is_symlink():
                    stats["ignored_directories"] += 1
                    continue
                kept_directories.append(directory_name)
            directory_names[:] = kept_directories

            for file_name in sorted(file_names):
                stats["visited_files"] += 1
                path = current_path / file_name
                relative_path = path.relative_to(repository_root).as_posix()

                if len(records) >= self.policy.max_files:
                    truncated = True
                    break
                if path.is_symlink():
                    stats["skipped_symlinks"] += 1
                    continue
                if _is_sensitive(path):
                    stats["skipped_sensitive"] += 1
                    continue

                try:
                    resolved = path.resolve(strict=True)
                    if not resolved.is_relative_to(repository_root):
                        stats["skipped_symlinks"] += 1
                        continue
                    size = resolved.stat().st_size
                except (OSError, RuntimeError):
                    stats["skipped_unreadable"] += 1
                    continue

                if size > self.policy.max_file_size_bytes:
                    stats["skipped_too_large"] += 1
                    continue
                if resolved.suffix.lower() in BINARY_SUFFIXES:
                    stats["skipped_binary"] += 1
                    continue

                try:
                    data = resolved.read_bytes()
                except OSError:
                    stats["skipped_unreadable"] += 1
                    continue
                if b"\x00" in data[:8_192]:
                    stats["skipped_binary"] += 1
                    continue
                try:
                    text = data.decode("utf-8-sig")
                except UnicodeDecodeError:
                    stats["skipped_unreadable"] += 1
                    continue

                category = _file_category(relative_path, resolved.name)
                language = _language_for(resolved)
                digest = hashlib.sha256(data).hexdigest()
                records.append(
                    RepositoryFile(
                        path=relative_path,
                        category=category,
                        language=language,
                        size_bytes=size,
                        sha256=digest,
                    )
                )
                stats["indexed_files"] += 1
                if language:
                    language_counts[language] += 1

                lowered_text = text.lower()
                lowered_name = resolved.name.lower()
                if _is_dependency_file(lowered_name):
                    dependency_files.add(relative_path)
                if category == FileCategory.TEST:
                    test_files.add(relative_path)
                if category == FileCategory.DOCUMENTATION:
                    documentation_files.add(relative_path)
                if category == FileCategory.CONFIGURATION:
                    configuration_files.add(relative_path)
                if category != FileCategory.TEST and _is_entrypoint(resolved.name, lowered_text):
                    entrypoints.add(relative_path)
                if language == "Python" or category == FileCategory.DEPENDENCY:
                    _detect_frameworks(lowered_text, frameworks)

            if truncated:
                break

        if truncated:
            warnings.append(f"scan stopped after reaching max_files={self.policy.max_files}")
        if not records:
            warnings.append("no readable text files were indexed")

        records.sort(key=lambda item: item.path)
        snapshot_id = _snapshot_id(records)
        return RepositoryManifest(
            repository_name=repository_root.name,
            snapshot_id=snapshot_id,
            git=_read_git_snapshot(repository_root),
            languages=dict(sorted(language_counts.items())),
            frameworks=sorted(frameworks),
            entrypoints=sorted(entrypoints),
            dependency_files=sorted(dependency_files),
            test_files=sorted(test_files),
            documentation_files=sorted(documentation_files),
            configuration_files=sorted(configuration_files),
            files=records,
            statistics=ScanStatistics(**stats),
            warnings=warnings,
        )


def _is_sensitive(path: Path) -> bool:
    lowered = path.name.lower()
    if lowered == ".env.example":
        return False
    if lowered == ".env" or lowered.startswith(".env."):
        return True
    return lowered in SENSITIVE_FILENAMES or path.suffix.lower() in SENSITIVE_SUFFIXES


def _is_dependency_file(lowered_name: str) -> bool:
    return (
        lowered_name in DEPENDENCY_FILENAMES
        or lowered_name.startswith("requirements")
        and lowered_name.endswith(".txt")
    )


def _file_category(relative_path: str, file_name: str) -> FileCategory:
    lowered_name = file_name.lower()
    parts = tuple(part.lower() for part in Path(relative_path).parts)
    if _is_dependency_file(lowered_name):
        return FileCategory.DEPENDENCY
    if "tests" in parts or "test" in parts or lowered_name.startswith("test_") or lowered_name.endswith("_test.py"):
        return FileCategory.TEST
    if lowered_name.startswith("readme") or "docs" in parts or Path(lowered_name).suffix in {".md", ".rst"}:
        return FileCategory.DOCUMENTATION
    if (
        lowered_name in CONFIG_FILENAMES
        or ".github" in parts
        or Path(lowered_name).suffix in {".toml", ".yaml", ".yml"}
    ):
        return FileCategory.CONFIGURATION
    return FileCategory.SOURCE


def _language_for(path: Path) -> str | None:
    lowered_name = path.name.lower()
    if lowered_name == "dockerfile":
        return "Dockerfile"
    if lowered_name == "makefile":
        return "Makefile"
    return LANGUAGES_BY_SUFFIX.get(path.suffix.lower())


def _is_entrypoint(file_name: str, lowered_text: str) -> bool:
    lowered_name = file_name.lower()
    return (
        lowered_name in ENTRYPOINT_FILENAMES
        or 'if __name__ == "__main__"' in lowered_text
        or "if __name__ == '__main__'" in lowered_text
    )


def _detect_frameworks(lowered_text: str, detected: set[str]) -> None:
    for framework, markers in FRAMEWORK_MARKERS.items():
        if any(marker in lowered_text for marker in markers):
            detected.add(framework)


def _snapshot_id(records: list[RepositoryFile]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(record.path.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(record.sha256.encode("ascii"))
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"


def _read_git_snapshot(root: Path) -> GitSnapshot:
    git_directory = root / ".git"
    if not git_directory.exists():
        return GitSnapshot()
    if not git_directory.is_dir():
        return GitSnapshot(available=True, note="Git worktree metadata files are not parsed in v0.1")

    head_path = git_directory / "HEAD"
    try:
        head = head_path.read_text(encoding="utf-8").strip()
    except OSError:
        return GitSnapshot(available=True, note="Git HEAD could not be read")

    if head.startswith("ref: "):
        reference = head.removeprefix("ref: ").strip()
        branch = reference.removeprefix("refs/heads/")
        commit = _read_git_reference(git_directory, reference)
        return GitSnapshot(
            available=True,
            branch=branch,
            commit=commit,
            dirty=None,
            note="Working-tree dirtiness is not evaluated during safe scanning",
        )
    return GitSnapshot(
        available=True,
        commit=head or None,
        dirty=None,
        note="Detached HEAD; working-tree dirtiness is not evaluated during safe scanning",
    )


def _read_git_reference(git_directory: Path, reference: str) -> str | None:
    reference_path = git_directory / Path(reference)
    try:
        if reference_path.is_file():
            return reference_path.read_text(encoding="utf-8").strip() or None
        packed_refs = git_directory / "packed-refs"
        if packed_refs.is_file():
            for line in packed_refs.read_text(encoding="utf-8").splitlines():
                if not line or line.startswith(("#", "^")):
                    continue
                commit, packed_reference = line.split(" ", 1)
                if packed_reference == reference:
                    return commit
    except (OSError, ValueError):
        return None
    return None
