"""验证 FastAPI 扫描接口的正常响应和目录边界。

测试通过受控临时工作区调用接口，确认合法相对路径能够生成仓库清单，同时越界、绝对路径和配置错误
会被拒绝。
"""

from pathlib import Path
from time import monotonic, sleep

from fastapi.testclient import TestClient

from vibeproof.interfaces.api import _analyst_policy, app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_web_workspace_and_assets_are_served() -> None:
    page = client.get("/")
    script = client.get("/static/app.js")
    styles = client.get("/static/styles.css")
    favicon = client.get("/static/favicon.svg")

    assert page.status_code == 200
    assert "接管一个 Python 仓库" in page.text
    assert "Agent 活动" in page.text
    assert script.status_code == 200
    assert "/api/v1/runs" in script.text
    assert "/api/v1/config" in script.text
    assert "analysisDepth" in script.text
    assert styles.status_code == 200
    assert "color-scheme: light" in styles.text
    assert "--activity: #898982" in styles.text
    assert favicon.status_code == 200


def test_web_configuration_reports_readiness_without_exposing_secrets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIBEPROOF_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("VIBEPROOF_AI_PROVIDER", "openai-compatible")
    monkeypatch.setenv("VIBEPROOF_AI_MODEL", "test-model")
    monkeypatch.setenv("VIBEPROOF_AI_BASE_URL", "https://relay.example/v1")
    monkeypatch.setenv("VIBEPROOF_AI_API_KEY", "secret-value")

    response = client.get("/api/v1/config")

    assert response.status_code == 200
    assert response.json() == {
        "workspaceConfigured": True,
        "workspaceName": tmp_path.name,
        "provider": "openai-compatible",
        "model": "test-model",
        "endpointConfigured": True,
        "apiKeyConfigured": True,
        "defaultAnalysisDepth": "deep",
    }
    assert "secret-value" not in response.text
    assert "relay.example" not in response.text


def test_web_analysis_profiles_use_bounded_agent_budgets() -> None:
    standard = _analyst_policy("standard")
    deep = _analyst_policy("deep")

    assert (standard.max_queries, standard.max_steps) == (5, 8)
    assert (deep.max_queries, deep.max_steps) == (6, 10)


def test_api_scan_is_confined_to_configured_root(tmp_path: Path, monkeypatch) -> None:
    workspace_root = tmp_path / "repositories"
    repository = workspace_root / "demo"
    repository.mkdir(parents=True)
    (repository / "main.py").write_text("print('hello')\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setenv("VIBEPROOF_WORKSPACE_ROOT", str(workspace_root))

    allowed = client.post("/api/v1/repositories/scan", json={"relativePath": "demo"})
    blocked = client.post("/api/v1/repositories/scan", json={"relativePath": "../outside"})

    assert allowed.status_code == 200
    assert allowed.json()["repository_name"] == "demo"
    assert blocked.status_code == 403


def test_api_scan_is_disabled_without_workspace_root(monkeypatch) -> None:
    monkeypatch.delenv("VIBEPROOF_WORKSPACE_ROOT", raising=False)

    response = client.post("/api/v1/repositories/scan", json={"relativePath": "."})

    assert response.status_code == 503


def test_api_runs_mock_takeover_and_returns_grounded_report(tmp_path: Path, monkeypatch) -> None:
    workspace_root = tmp_path / "repositories"
    repository = workspace_root / "demo"
    repository.mkdir(parents=True)
    (repository / "app.py").write_text(
        "def create_app():\n    return {'status': 'ok'}\n",
        encoding="utf-8",
    )
    (repository / "test_app.py").write_text(
        "from app import create_app\n\n\ndef test_create_app():\n    assert create_app()['status'] == 'ok'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VIBEPROOF_WORKSPACE_ROOT", str(workspace_root))
    monkeypatch.setenv("VIBEPROOF_DATABASE", str(tmp_path / "web-index.sqlite3"))

    response = client.post(
        "/api/v1/repositories/takeover",
        json={
            "relativePath": "demo",
            "provider": "mock",
            "executeRuntime": False,
            "runtimeCheck": "pytest",
        },
    )

    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "COMPLETED"
    assert report["architecture"]["claims"]
    assert report["learning_plan"]["units"]
    assert report["runtime"]["status"] == "PLANNED"
    assert [step["stage"] for step in report["steps"]] == [
        "SCAN",
        "INDEX",
        "ANALYZE",
        "LEARNING_PLAN",
        "RUNTIME_PLAN",
        "REPORT",
    ]


def test_api_reads_only_bounded_source_inside_repository(tmp_path: Path, monkeypatch) -> None:
    workspace_root = tmp_path / "repositories"
    repository = workspace_root / "demo"
    repository.mkdir(parents=True)
    (repository / "app.py").write_text("line one\nline two\nline three\n", encoding="utf-8")
    (workspace_root / "secret.py").write_text("outside\n", encoding="utf-8")
    monkeypatch.setenv("VIBEPROOF_WORKSPACE_ROOT", str(workspace_root))

    allowed = client.post(
        "/api/v1/repositories/source",
        json={"relativePath": "demo", "sourcePath": "app.py", "startLine": 2, "endLine": 3},
    )
    blocked = client.post(
        "/api/v1/repositories/source",
        json={"relativePath": "demo", "sourcePath": "../secret.py", "startLine": 1, "endLine": 1},
    )

    assert allowed.status_code == 200
    assert allowed.json() == {
        "sourcePath": "app.py",
        "startLine": 2,
        "endLine": 3,
        "content": "line two\nline three",
    }
    assert blocked.status_code == 403


def test_background_run_can_be_polled_reviewed_exported_and_deleted(tmp_path: Path, monkeypatch) -> None:
    workspace_root = tmp_path / "repositories"
    repository = workspace_root / "demo"
    repository.mkdir(parents=True)
    (repository / "app.py").write_text("def create_app():\n    return {'status': 'ok'}\n", encoding="utf-8")
    (repository / "test_app.py").write_text(
        "from app import create_app\n\n\ndef test_create_app():\n    assert create_app()['status'] == 'ok'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VIBEPROOF_WORKSPACE_ROOT", str(workspace_root))
    monkeypatch.setenv("VIBEPROOF_DATABASE", str(tmp_path / "index.sqlite3"))
    monkeypatch.setenv("VIBEPROOF_RUNS_DIRECTORY", str(tmp_path / "runs"))

    started = client.post(
        "/api/v1/runs",
        json={
            "relativePath": "demo",
            "provider": "mock",
            "executeRuntime": True,
            "runtimeCheck": "pytest-collect",
        },
    )
    assert started.status_code == 202
    run_id = started.json()["run_id"]
    record = _wait_for_run(run_id)

    assert record["status"] == "COMPLETED"
    assert record["report"]["architecture"]["claims"]
    assert record["report"]["runtime"]["status"] == "PASSED"
    assert record["report"]["runtime"]["plan"]["check"] == "PYTEST_COLLECT"
    assert [step["stage"] for step in record["steps"]][-1] == "REPORT"
    assert client.get("/api/v1/runs").json()[0]["run_id"] == run_id

    tutor_retry = client.post(f"/api/v1/runs/{run_id}/retry", json={"stage": "learning"})
    assert tutor_retry.status_code == 202
    record = _wait_for_run(run_id)
    assert record["status"] == "COMPLETED"
    assert sum(step["stage"] == "ANALYZE" for step in record["steps"]) == 1
    assert sum(step["stage"] == "LEARNING_PLAN" for step in record["steps"]) == 2

    runtime_retry = client.post(f"/api/v1/runs/{run_id}/retry", json={"stage": "runtime"})
    assert runtime_retry.status_code == 202
    record = _wait_for_run(run_id)
    assert record["status"] == "COMPLETED"
    assert sum(step["stage"] == "ANALYZE" for step in record["steps"]) == 1
    assert sum(step["stage"] == "RUNTIME_EXECUTION" for step in record["steps"]) == 2

    answers = [
        {"question_id": question["question_id"], "answer": ""}
        for question in record["report"]["learning_plan"]["questions"]
    ]
    reviewed = client.post(
        f"/api/v1/runs/{run_id}/review",
        json={"answers": answers, "provider": "mock"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["review"]["mode"] == "STRUCTURE_ONLY"
    assert len(client.get(f"/api/v1/runs/{run_id}").json()["attempts"]) == 1

    exported_json = client.get(f"/api/v1/runs/{run_id}/export?format=json")
    exported_markdown = client.get(f"/api/v1/runs/{run_id}/export?format=markdown")
    assert exported_json.status_code == 200
    assert exported_json.json()["run_id"] == run_id
    assert "# Repository takeover report" in exported_markdown.text
    assert "# Learning review" in exported_markdown.text

    deleted = client.delete(f"/api/v1/runs/{run_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/runs/{run_id}").status_code == 404


def _wait_for_run(run_id: str) -> dict:
    deadline = monotonic() + 5
    while monotonic() < deadline:
        response = client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200
        record = response.json()
        if record["status"] not in {"PENDING", "RUNNING"}:
            return record
        sleep(0.02)
    raise AssertionError("background run did not finish")
