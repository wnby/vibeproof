"""提供 VibeProof 本地 Web 工作台与范围受限的仓库接管 API。

浏览器只能访问 ``VIBEPROOF_WORKSPACE_ROOT`` 下的相对路径。API 复用现有扫描器、
证据索引、架构分析、学习计划和运行验证服务；模型密钥只从服务端环境变量读取，
不会由浏览器请求传入或返回。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from vibeproof import __version__
from vibeproof.agents.analyst import AnalystPolicy
from vibeproof.config import ConfigurationError, Settings
from vibeproof.core.models import RepositoryManifest, RuntimeCheck, TakeoverReport
from vibeproof.llm.client import create_model_client
from vibeproof.repository.scanner import RepositoryScanner
from vibeproof.repository.store import EvidenceStore
from vibeproof.workflows.takeover import TakeoverCoordinator, TakeoverPolicy

WEB_ROOT = Path(__file__).parents[1] / "web"

app = FastAPI(title="VibeProof", version=__version__)
app.mount("/static", StaticFiles(directory=WEB_ROOT), name="static")


class ApiModel(BaseModel):
    """API 请求响应的共同严格校验基类。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class ScanRequest(ApiModel):
    """用户在已配置工作区内选择的仓库相对路径。"""

    relative_path: str = Field(default=".", alias="relativePath", min_length=1, max_length=500)


class TakeoverRequest(ScanRequest):
    """启动完整接管所需的模型和运行验证选项。"""

    provider: Literal["mock", "openai-compatible", "ollama"] = "mock"
    model: str | None = Field(default=None, min_length=1, max_length=200)
    analysis_depth: Literal["standard", "deep"] = Field(default="deep", alias="analysisDepth")
    execute_runtime: bool = Field(default=False, alias="executeRuntime")
    runtime_check: Literal["pytest", "pytest-collect"] = Field(default="pytest", alias="runtimeCheck")


class WebConfiguration(ApiModel):
    """浏览器安全可见的服务端配置摘要；只返回是否配置密钥，不返回密钥或工作区绝对路径。"""

    workspace_configured: bool = Field(alias="workspaceConfigured")
    workspace_name: str | None = Field(alias="workspaceName")
    provider: str
    model: str | None
    endpoint_configured: bool = Field(alias="endpointConfigured")
    api_key_configured: bool = Field(alias="apiKeyConfigured")
    default_analysis_depth: Literal["deep"] = Field(default="deep", alias="defaultAnalysisDepth")


class SourceExcerptRequest(ScanRequest):
    """查看某条引用对应源码行的受限请求。"""

    source_path: str = Field(alias="sourcePath", min_length=1, max_length=500)
    start_line: int = Field(default=1, alias="startLine", ge=1)
    end_line: int = Field(default=120, alias="endLine", ge=1)


class SourceExcerpt(ApiModel):
    """返回给前端的仓库相对路径和源码片段。"""

    source_path: str = Field(alias="sourcePath")
    start_line: int = Field(alias="startLine")
    end_line: int = Field(alias="endLine")
    content: str


@app.get("/", include_in_schema=False)
def web_app() -> FileResponse:
    """返回无需前端构建链的单页工作台。"""
    return FileResponse(WEB_ROOT / "index.html", media_type="text/html")


@app.get("/health")
def health() -> dict[str, str]:
    """供本地启动和部署检查使用的轻量健康接口。"""
    return {"status": "ok", "service": "vibeproof", "version": __version__}


@app.get("/api/v1/config", response_model=WebConfiguration)
def web_configuration() -> WebConfiguration:
    """告诉页面真实模型是否就绪，同时避免暴露密钥、接口地址和本机绝对目录。"""
    settings = Settings.from_env()
    return WebConfiguration(
        workspaceConfigured=settings.workspace_root is not None,
        workspaceName=settings.workspace_root.name if settings.workspace_root else None,
        provider=settings.ai_provider,
        model=settings.ai_model or None,
        endpointConfigured=bool(settings.ai_base_url),
        apiKeyConfigured=bool(settings.ai_api_key),
        defaultAnalysisDepth="deep",
    )


@app.post("/api/v1/repositories/scan", response_model=RepositoryManifest)
def scan_repository(request: ScanRequest) -> RepositoryManifest:
    """扫描工作区内的一个仓库，但不建立索引或调用 Agent。"""
    target = _resolve_repository(request.relative_path)
    try:
        return RepositoryScanner().scan(target)
    except (NotADirectoryError, PermissionError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@app.post("/api/v1/repositories/takeover", response_model=TakeoverReport)
def takeover_repository(request: TakeoverRequest) -> TakeoverReport:
    """组装配置与模型客户端，执行前端使用的完整 Takeover 工作流。"""
    target = _resolve_repository(request.relative_path)
    try:
        settings = Settings.from_env()
        analyst_model = create_model_client(
            provider=request.provider,
            model=request.model,
            task="analyst",
            settings=settings,
        )
        tutor_model = create_model_client(
            provider=request.provider,
            model=request.model,
            task="tutor",
            settings=settings,
        )
    except ConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    runtime_check = RuntimeCheck.PYTEST if request.runtime_check == "pytest" else RuntimeCheck.PYTEST_COLLECT
    try:
        return TakeoverCoordinator(
            store=EvidenceStore(settings.database),
            model=analyst_model,
            tutor_model=tutor_model,
            policy=TakeoverPolicy(
                analyst_policy=_analyst_policy(request.analysis_depth),
                runtime_check=runtime_check,
                execute_runtime=request.execute_runtime,
            ),
        ).run(target)
    except (OSError, PermissionError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@app.post("/api/v1/repositories/source", response_model=SourceExcerpt)
def read_source_excerpt(request: SourceExcerptRequest) -> SourceExcerpt:
    """按引用行号读取源码，同时确保路径和行数都留在所选仓库边界内。"""
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
    configured_root = Settings.from_env().workspace_root
    if configured_root is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VIBEPROOF_WORKSPACE_ROOT must be configured before repository access is enabled",
        )
    try:
        allowed_root = configured_root.resolve(strict=True)
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


def _analyst_policy(depth: Literal["standard", "deep"]) -> AnalystPolicy:
    """把 Web 的可读分析档位转换为受控 Agent 预算，不向浏览器开放任意数值。"""
    if depth == "deep":
        return AnalystPolicy(max_steps=10, max_queries=6)
    return AnalystPolicy()
