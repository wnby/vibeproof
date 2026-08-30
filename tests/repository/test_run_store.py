"""验证 Web Run 的原子 JSON 持久化、恢复、列表和删除。"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from vibeproof.core.models import WebRunConfiguration, WebRunRecord, WebRunStatus
from vibeproof.repository.run_store import RunNotFoundError, RunStore


def test_run_store_round_trips_lists_and_deletes_records(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    record = WebRunRecord(
        configuration=WebRunConfiguration(relative_path="demo", provider="mock"),
    )

    store.create(record)
    saved = store.save(record.model_copy(update={"status": WebRunStatus.COMPLETED}))

    assert store.load(record.run_id) == saved
    summaries = store.list_summaries()
    assert summaries[0].run_id == record.run_id
    assert summaries[0].repository_name == "demo"
    assert summaries[0].status == WebRunStatus.COMPLETED

    store.delete(record.run_id)
    with pytest.raises(RunNotFoundError):
        store.load(record.run_id)


def test_run_store_rejects_invalid_ids_and_duplicate_creation(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    record = WebRunRecord(configuration=WebRunConfiguration(relative_path="demo", provider="mock"))
    store.create(record)

    with pytest.raises(ValueError, match="already exists"):
        store.create(record)
    with pytest.raises(ValueError, match="invalid format"):
        store.load("../outside")


def test_run_store_never_replaces_valid_history_with_unvalidated_model_copy(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    record = WebRunRecord(configuration=WebRunConfiguration(relative_path="demo", provider="mock"))
    store.create(record)
    invalid_configuration = record.configuration.model_copy(update={"relative_path": ""})

    with pytest.raises(ValidationError):
        store.save(record.model_copy(update={"configuration": invalid_configuration}))

    assert store.load(record.run_id) == record
