import random

import pytest

from surveycore.answers import choose_weighted, limit_multiple_selection


def test_choose_weighted_uses_weighted_index() -> None:
    random.seed(3)
    assert choose_weighted([0.0, 1.0, 0.0]) == 1


@pytest.mark.parametrize(
    ("indices", "minimum", "maximum", "expected"),
    [
        ([0, 1, 2], 1, 2, [0, 1]),
        ([0, 1], 0, 0, []),
        ([0, 1, 2, 3], 1, 4, [0, 1, 2, 3]),
    ],
)
def test_limit_multiple_selection_respects_bounds(
    indices: list[int], minimum: int, maximum: int, expected: list[int]
) -> None:
    assert limit_multiple_selection(indices, minimum=minimum, maximum=maximum) == tuple(expected)
