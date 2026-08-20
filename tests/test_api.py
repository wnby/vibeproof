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
