"""提供范围受限的 FastAPI 仓库扫描接口。

接口只允许访问配置工作区内的相对路径，并调用静态扫描器返回仓库清单；它不会执行目标代码、安装
依赖或向调用方开放任意文件系统路径。
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from vibeproof import __version__
from vibeproof.scanner import RepositoryScanner
from vibeproof.schemas import RepositoryManifest

app = FastAPI(title="VibeProof", version=__version__)


class ScanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    relative_path: str = Field(default=".", alias="relativePath", min_length=1)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "vibeproof", "version": __version__}


@app.post("/api/v1/repositories/scan", response_model=RepositoryManifest)
def scan_repository(request: ScanRequest) -> RepositoryManifest:
    configured_root = os.getenv("VIBEPROOF_WORKSPACE_ROOT", "").strip()
    if not configured_root:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VIBEPROOF_WORKSPACE_ROOT must be configured before API scanning is enabled",
        )
    try:
        allowed_root = Path(configured_root).expanduser().resolve(strict=True)
        target = (allowed_root / request.relative_path).resolve(strict=True)
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="repository path was not found") from exc
    if not allowed_root.is_dir():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="configured workspace root is invalid"
        )
    if not target.is_relative_to(allowed_root):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="repository path escapes the workspace root")
    try:
        return RepositoryScanner().scan(target)
    except (NotADirectoryError, PermissionError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
