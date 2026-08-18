import json
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
