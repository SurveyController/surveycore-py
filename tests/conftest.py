from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def patch_attrs(monkeypatch: pytest.MonkeyPatch):
    def apply(*entries: tuple[object, str, object]) -> None:
        for target, name, value in entries:
            monkeypatch.setattr(target, name, value)

    return apply


@pytest.fixture
def make_mock_event():
    def factory(
        *,
        is_set: bool = False,
        wait_return: bool = False,
        spec: object = threading.Event,
    ) -> MagicMock:
        event = MagicMock(spec=spec)
        event.is_set.return_value = is_set
        event.wait.return_value = wait_return
        return event

    return factory
