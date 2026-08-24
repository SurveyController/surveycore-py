from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def completed_results(
    target: int,
    concurrency: int,
    operation: Callable[[int], Awaitable[T]],
) -> AsyncGenerator[T]:
    """Run a bounded number of attempts and yield them in completion order."""
    semaphore = asyncio.Semaphore(max(1, int(concurrency)))

    async def bounded(index: int) -> T:
        async with semaphore:
            return await operation(index)

    tasks = [asyncio.create_task(bounded(index)) for index in range(1, max(1, int(target)) + 1)]
    try:
        for task in asyncio.as_completed(tasks):
            yield await task
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
