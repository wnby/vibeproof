"""验证 FastAPI 扫描接口的正常响应和目录边界。

测试通过受控临时工作区调用接口，确认合法相对路径能够生成仓库清单，同时越界、绝对路径和配置错误
会被拒绝。
"""

from pathlib import Path

from fastapi.testclient import TestClient

from vibeproof.api import app

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
    assert "/api/v1/repositories/takeover" in script.text
    assert styles.status_code == 200
    assert "--activity: #8c8c8c" in styles.text
    assert favicon.status_code == 200


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
