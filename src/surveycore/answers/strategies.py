from __future__ import annotations

import random
from collections.abc import Sequence


def choose_weighted(weights: Sequence[float], *, rng: random.Random | None = None) -> int:
    """Return an index using non-negative relative weights."""
    values = [max(0.0, float(value)) for value in weights]
    if not values or sum(values) <= 0:
        raise ValueError("至少需要一个正权重")
    picker = rng or random
    return picker.choices(range(len(values)), weights=values, k=1)[0]


def limit_multiple_selection(indices: Sequence[int], *, minimum: int = 1, maximum: int | None = None) -> tuple[int, ...]:
    """Normalize multiple-choice selections to a bounded, duplicate-free tuple."""
    unique = tuple(dict.fromkeys(int(index) for index in indices))
    if len(unique) < minimum:
        raise ValueError("多选答案少于最小选择数")
    if maximum is not None and len(unique) > maximum:
        return unique[:maximum]
    return unique
