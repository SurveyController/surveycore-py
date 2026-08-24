import asyncio

import pytest

from surveycore.runtime import completed_results


@pytest.mark.asyncio
async def test_results_are_yielded_in_completion_order_with_bounded_concurrency() -> None:
    active = 0
    maximum_active = 0

    async def operation(index: int) -> int:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        try:
            await asyncio.sleep({1: 0.03, 2: 0.01, 3: 0.02}[index])
            return index
        finally:
            active -= 1

    results = [item async for item in completed_results(3, 2, operation)]
    assert results == [2, 1, 3]
    assert maximum_active == 2


@pytest.mark.asyncio
async def test_closing_iterator_cancels_pending_attempts() -> None:
    cancelled = asyncio.Event()

    async def operation(index: int) -> int:
        if index == 1:
            return index
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return index

    iterator = completed_results(2, 2, operation)
    assert await anext(iterator) == 1
    await iterator.aclose()
    assert cancelled.is_set()
