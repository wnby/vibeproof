"""提供多组件异步调用场景，用于评估 Agent 对控制流和职责边界的学习覆盖。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerResult:
    worker: str
    value: str


class Worker:
    def __init__(self, name: str):
        self.name = name

    async def run(self, value: str) -> WorkerResult:
        await asyncio.sleep(0)
        return WorkerResult(worker=self.name, value=value.upper())


class Coordinator:
    def __init__(self, workers: list[Worker]):
        self.workers = workers

    async def dispatch(self, value: str) -> list[WorkerResult]:
        return list(await asyncio.gather(*(worker.run(value) for worker in self.workers)))
