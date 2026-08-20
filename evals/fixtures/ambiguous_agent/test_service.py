"""验证异步协调器会并发调用所有 Worker 并保留各自身份。"""

import asyncio

from service import Coordinator, Worker


def test_dispatch_collects_every_worker() -> None:
    results = asyncio.run(Coordinator([Worker("a"), Worker("b")]).dispatch("ready"))

    assert [(item.worker, item.value) for item in results] == [("a", "READY"), ("b", "READY")]
