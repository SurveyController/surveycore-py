from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UserAgentProfile:
    category: str
    preset_key: str
    ua: str
    label: str
