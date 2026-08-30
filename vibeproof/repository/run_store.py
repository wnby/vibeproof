"""使用本地 JSON 文件保存 Web 接管任务和学习尝试。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from pydantic import ValidationError

from vibeproof.core.models import WebRunRecord, WebRunSummary

_STORE_LOCK = RLock()


class RunNotFoundError(LookupError):
    """请求的 Web Run 不存在于本地持久化目录。"""


class RunStore:
    """以单文件原子替换方式持久化 Run，支持刷新恢复、列表和删除。"""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory).expanduser().resolve()

    def create(self, record: WebRunRecord) -> WebRunRecord:
        """创建一条新 Run；重复 ID 会被拒绝而不是覆盖历史。"""
        with _STORE_LOCK:
            if self._path(record.run_id).exists():
                raise ValueError(f"run already exists: {record.run_id}")
            self._write(record)
        return record

    def save(self, record: WebRunRecord) -> WebRunRecord:
        """更新时间并原子替换一条已经存在的 Run。"""
        with _STORE_LOCK:
            if not self._path(record.run_id).is_file():
                raise RunNotFoundError(f"run was not found: {record.run_id}")
            updated = record.model_copy(update={"updated_at": datetime.now(UTC)})
            self._write(updated)
        return updated

    def load(self, run_id: str) -> WebRunRecord:
        """严格解析一条 Run，损坏的 JSON 不会伪装成有效历史。"""
        with _STORE_LOCK:
            path = self._path(run_id)
            if not path.is_file():
                raise RunNotFoundError(f"run was not found: {run_id}")
            try:
                return WebRunRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValidationError) as exc:
                raise ValueError(f"stored run is invalid: {run_id}: {exc}") from exc

    def list_summaries(self, limit: int = 20) -> list[WebRunSummary]:
        """按最近更新时间倒序列出有限数量的任务摘要。"""
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        with _STORE_LOCK:
            if not self.directory.is_dir():
                return []
            records: list[WebRunRecord] = []
            for path in self.directory.glob("run_*.json"):
                try:
                    records.append(WebRunRecord.model_validate_json(path.read_text(encoding="utf-8")))
                except (OSError, ValidationError):
                    continue
        records.sort(key=lambda item: item.updated_at, reverse=True)
        return [_summary(item) for item in records[:limit]]

    def delete(self, run_id: str) -> None:
        """删除一个明确 ID 对应的历史文件；运行中的任务由上层拒绝删除。"""
        path = self._path(run_id)
        with _STORE_LOCK:
            if not path.is_file():
                raise RunNotFoundError(f"run was not found: {run_id}")
            path.unlink()

    def _path(self, run_id: str) -> Path:
        if not run_id.startswith("run_") or not run_id[4:].isalnum():
            raise ValueError("run_id has an invalid format")
        return self.directory / f"{run_id}.json"

    def _write(self, record: WebRunRecord) -> None:
        validated = WebRunRecord.model_validate(record.model_dump(mode="json"))
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self._path(validated.run_id)
        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(validated.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(destination)


def _summary(record: WebRunRecord) -> WebRunSummary:
    repository_name = record.report.repository_name if record.report else record.configuration.relative_path
    return WebRunSummary(
        run_id=record.run_id,
        repository_name=repository_name,
        relative_path=record.configuration.relative_path,
        status=record.status,
        active_stage=record.active_stage,
        attempt_count=len(record.attempts),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
