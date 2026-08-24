from __future__ import annotations

from dataclasses import dataclass

from surveycore.providers.answering import selection
from surveycore.providers.runtime_state import ProviderRuntimeStateStore
from surveycore.tencent.provider.answering_rules import (
    apply_multiple_constraints,
    normalize_selected_indices,
)


def test_selection_helpers_normalize_bounds_and_weights(monkeypatch) -> None:
    assert selection.coerce_positive_int("3", 1) == 3
    assert selection.coerce_positive_int("bad", 2) == 2
    assert selection.valid_forced_choice_index("1", 3) == 1
    assert selection.valid_forced_choice_index(3, 3) is None
    assert selection.format_weight_value(12.340000) == "12.34"
    assert selection.format_weight_value(float("nan")) == "随机"
    assert selection.resolve_selected_weight_text(1, [10, 20], None) == "20"

    monkeypatch.setattr(selection.random, "uniform", lambda *_args: 0.0)
    assert selection.positive_multiple_indexes([100, 0, 50], 3) == [0, 2]


def test_multiple_selection_limits_add_and_trim_choices(monkeypatch) -> None:
    monkeypatch.setattr(selection, "positive_multiple_indexes", lambda *_args: [0, 1, 2])
    monkeypatch.setattr(selection.random, "sample", lambda values, count: values[:count])
    assert selection.positive_multiple_indexes_with_limits(
        [100, 100, 100],
        3,
        min_limit=1,
        max_limit=2,
    ) == [0, 1]

    monkeypatch.setattr(selection, "positive_multiple_indexes", lambda *_args: [0])
    monkeypatch.setattr(selection.random, "shuffle", lambda values: None)
    assert selection.positive_multiple_indexes_with_limits(
        [100, 50, 0],
        3,
        min_limit=3,
        max_limit=3,
    ) == [0, 1, 2]


def test_tencent_multiple_constraints_preserve_required_and_blocked() -> None:
    assert normalize_selected_indices([2, 1, 2, -1, 9], 3) == [1, 2]
    assert apply_multiple_constraints(
        selected_indices=[0, 1, 2],
        option_count=4,
        min_required=3,
        max_allowed=3,
        required_indices=[3],
        blocked_indices=[1],
        positive_priority_indices=[2, 0],
    ) == [0, 2, 3]


@dataclass
class _State:
    value: int = 0


def test_provider_runtime_state_store_handles_weak_and_nonweak_keys() -> None:
    weak_store = ProviderRuntimeStateStore("qq", _State)

    class Driver:
        pass

    driver = Driver()
    state = weak_store.get_or_create(driver)
    state.value = 7
    assert weak_store.get_or_create(driver) is state
    stored = weak_store.peek(driver)
    assert stored is not None
    assert stored.value == 7
    assert weak_store.snapshot_size() == 1
    weak_store.clear(driver)
    assert weak_store.peek(driver) is None

    fallback_store = ProviderRuntimeStateStore("wjx", _State)
    nonweak_driver: list[str] = []
    fallback = fallback_store.get_or_create(nonweak_driver)
    assert fallback_store.peek(nonweak_driver) is fallback
    fallback_store.clear(nonweak_driver)
    assert fallback_store.snapshot_size() == 0
