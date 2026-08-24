from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class SubmitProxyUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class SubmitProxyLease:
    address: str | None = None
    provider: str = "injected"


def mark_submit_proxy_success(*_args: Any, **_kwargs: Any) -> None:
    return None


def release_submit_proxy(*_args: Any, **_kwargs: Any) -> None:
    return None


__all__ = ["SubmitProxyLease", "SubmitProxyUnavailableError", "mark_submit_proxy_success", "release_submit_proxy"]
