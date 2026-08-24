import asyncio

import pytest

from surveycore.core.modes.duration_control import (
    sample_answer_duration_seconds,
    wait_answer_duration_seconds,
)


def test_duration_sampling_stays_in_range() -> None:
    assert all(10 <= sample_answer_duration_seconds((10, 20)) <= 20 for _ in range(100))


@pytest.mark.asyncio
async def test_duration_wait_can_be_cancelled() -> None:
    stop = asyncio.Event()
    task = asyncio.create_task(wait_answer_duration_seconds(stop, 30))
    stop.set()
    assert await asyncio.wait_for(task, timeout=1)
