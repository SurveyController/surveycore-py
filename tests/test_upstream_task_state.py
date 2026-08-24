from __future__ import annotations

import threading
import time

import pytest

from surveycore.core.task import ExecutionConfig, ExecutionState


class TestExecutionState:
    def test_wait_for_runtime_change_returns_after_notification(self) -> None:
        state = ExecutionState()
        result: dict[str, bool] = {}

        def waiter() -> None:
            result["value"] = state.wait_for_runtime_change(timeout=1.0)

        worker = threading.Thread(target=waiter, name="RuntimeWaiter")
        worker.start()
        time.sleep(0.02)
        state.notify_runtime_change()
        worker.join(timeout=1.0)

        assert not worker.is_alive()
        assert result["value"] is False

    def test_wait_for_runtime_change_observes_stop_signal(self) -> None:
        state = ExecutionState()
        stop_signal = threading.Event()
        result: dict[str, bool] = {}

        def waiter() -> None:
            result["value"] = state.wait_for_runtime_change(
                stop_signal=stop_signal,
                timeout=1.0,
            )

        worker = threading.Thread(target=waiter, name="RuntimeStopWaiter")
        worker.start()
        time.sleep(0.02)
        stop_signal.set()
        state.notify_runtime_change()
        worker.join(timeout=1.0)

        assert not worker.is_alive()
        assert result["value"] is True

    def test_joint_sample_reservations_are_unique_and_committed(self) -> None:
        state = ExecutionState()

        assert state.reserve_joint_sample(2, thread_name="Worker-1") == 0
        assert state.reserve_joint_sample(2, thread_name="Worker-2") == 1
        assert state.reserve_joint_sample(2, thread_name="Worker-3") is None
        assert state.mark_joint_sample_answering("Worker-2")
        assert state.commit_joint_sample("Worker-1") == 0
        assert state.release_joint_sample("Worker-2") == 1
        assert not state.is_joint_sample_quota_exhausted(2)

    def test_distribution_choices_commit_atomically(self) -> None:
        state = ExecutionState()
        state.reset_pending_distribution("Worker-1")
        state.append_pending_distribution_choice("q1", 1, 3, "Worker-1")
        state.append_pending_distribution_choice("q1", 2, 3, "Worker-1")

        assert state.commit_pending_distribution("Worker-1") == 2
        assert state.snapshot_distribution_stats("q1", 3) == (2, [0, 1, 1])
        assert state.commit_pending_distribution("Worker-1") == 0

    def test_thread_progress_clamps_steps_and_sorts_unknown_last(self) -> None:
        state = ExecutionState()
        state.update_thread_step("Worker-2", 99, 3, status_text="running", running=True)
        state.update_thread_status("Worker-?", "waiting", running=False)
        state.update_thread_step("Worker-1", 1, 4, status_text="step", running=True)

        rows = state.snapshot_thread_progress()
        assert [row["thread_name"] for row in rows] == ["Worker-1", "Worker-2", "Worker-?"]
        assert rows[1]["step_current"] == 3
        assert rows[1]["step_percent"] == 100

    def test_free_ai_prefill_cache_normalizes_and_clears_values(self) -> None:
        state = ExecutionState()
        state.set_free_ai_prefill_answers(" slot-1 ", {1: (" 答案 ", ""), -1: ("bad",)})
        state.set_free_ai_option_fill_prefill_answers(
            "slot-1",
            {(1, 0): " 补充 ", (0, 1): "bad"},
        )

        assert state.get_free_ai_prefill_answer("slot-1", 1) == ("答案",)
        assert state.get_free_ai_option_fill_prefill_answer("slot-1", 1, 0) == "补充"
        state.clear_free_ai_prefill_answers("slot-1")
        assert state.get_free_ai_prefill_answer("slot-1", 1) is None
        assert state.get_free_ai_option_fill_prefill_answer("slot-1", 1, 0) is None

    def test_setting_config_field_on_state_raises_clear_error(self) -> None:
        state = ExecutionState(config=ExecutionConfig())
        with pytest.raises(AttributeError, match="state.config.target_num"):
            state.target_num = 10  # type: ignore[attr-defined]
