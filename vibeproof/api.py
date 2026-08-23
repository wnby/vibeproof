"""提供 VibeProof 本地 Web 工作台与范围受限的仓库接管 API。

浏览器只能访问 ``VIBEPROOF_WORKSPACE_ROOT`` 下的相对路径。API 复用现有扫描器、
证据索引、架构分析、学习计划和运行验证服务；模型密钥只从服务端环境变量读取，
不会由浏览器请求传入或返回。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from vibeproof import __version__
from vibeproof.coordinator import TakeoverCoordinator, TakeoverPolicy
from vibeproof.evidence_store import EvidenceStore
from vibeproof.model_client import ModelConfigurationError, create_model_client
from vibeproof.scanner import RepositoryScanner
from vibeproof.schemas import RepositoryManifest, RuntimeCheck, TakeoverReport

WEB_ROOT = Path(__file__).with_name("web")
DEFAULT_DATABASE = Path(".vibeproof/index.sqlite3")

app = FastAPI(title="VibeProof", version=__version__)
app.mount("/static", StaticFiles(directory=WEB_ROOT), name="static")


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class ScanRequest(ApiModel):
    relative_path: str = Field(default=".", alias="relativePath", min_length=1, max_length=500)


class TakeoverRequest(ScanRequest):
    provider: Literal["mock", "openai-compatible", "ollama"] = "mock"
    model: str | None = Field(default=None, min_length=1, max_length=200)
    execute_runtime: bool = Field(default=False, alias="executeRuntime")
    runtime_check: Literal["pytest", "pytest-collect"] = Field(default="pytest", alias="runtimeCheck")


class SourceExcerptRequest(ScanRequest):
    source_path: str = Field(alias="sourcePath", min_length=1, max_length=500)
    start_line: int = Field(default=1, alias="startLine", ge=1)
    end_line: int = Field(default=120, alias="endLine", ge=1)


class SourceExcerpt(ApiModel):
    source_path: str = Field(alias="sourcePath")
    start_line: int = Field(alias="startLine")
    end_line: int = Field(alias="endLine")
    content: str


@app.get("/", include_in_schema=False)
def web_app() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html", media_type="text/html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "vibeproof", "version": __version__}


@app.post("/api/v1/repositories/scan", response_model=RepositoryManifest)
def scan_repository(request: ScanRequest) -> RepositoryManifest:
    target = _resolve_repository(request.relative_path)
    try:
        return RepositoryScanner().scan(target)
    except (NotADirectoryError, PermissionError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@app.post("/api/v1/repositories/takeover", response_model=TakeoverReport)
def takeover_repository(request: TakeoverRequest) -> TakeoverReport:
    target = _resolve_repository(request.relative_path)
    try:
        analyst_model = create_model_client(provider=request.provider, model=request.model, task="analyst")
        tutor_model = create_model_client(provider=request.provider, model=request.model, task="tutor")
    except ModelConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    database = Path(os.getenv("VIBEPROOF_DATABASE", str(DEFAULT_DATABASE))).expanduser()
    runtime_check = RuntimeCheck.PYTEST if request.runtime_check == "pytest" else RuntimeCheck.PYTEST_COLLECT
    try:
        return TakeoverCoordinator(
            store=EvidenceStore(database),
            model=analyst_model,
            tutor_model=tutor_model,
            policy=TakeoverPolicy(
                runtime_check=runtime_check,
                execute_runtime=request.execute_runtime,
            ),
        ).run(target)
    except (OSError, PermissionError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@app.post("/api/v1/repositories/source", response_model=SourceExcerpt)
def read_source_excerpt(request: SourceExcerptRequest) -> SourceExcerpt:
    repository = _resolve_repository(request.relative_path)
    try:
        source = (repository / request.source_path).resolve(strict=True)
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source file was not found") from exc
    if not source.is_relative_to(repository):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="source path escapes the repository")
    if not source.is_file():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source path is not a file")
    if request.end_line < request.start_line or request.end_line - request.start_line >= 240:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source excerpt must be an ordered range of at most 240 lines",
        )
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source file is not UTF-8 text") from exc
    selected = lines[request.start_line - 1 : request.end_line]
    actual_end = request.start_line + len(selected) - 1 if selected else request.start_line
    return SourceExcerpt(
        sourcePath=source.relative_to(repository).as_posix(),
        startLine=request.start_line,
        endLine=actual_end,
        content="\n".join(selected),
    )


def _resolve_repository(relative_path: str) -> Path:
    configured_root = os.getenv("VIBEPROOF_WORKSPACE_ROOT", "").strip()
    if not configured_root:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VIBEPROOF_WORKSPACE_ROOT must be configured before repository access is enabled",
        )
    try:
        allowed_root = Path(configured_root).expanduser().resolve(strict=True)
        target = (allowed_root / relative_path).resolve(strict=True)
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="repository path was not found") from exc
    if not allowed_root.is_dir():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="configured workspace root is invalid",
        )
    if not target.is_relative_to(allowed_root):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="repository path escapes the workspace root")
    if not target.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repository path is not a directory")
    return target
