from __future__ import annotations

from surveycore.core.reverse_fill.runtime import resolve_current_reverse_fill_answer
from surveycore.core.reverse_fill.schema import (
    REVERSE_FILL_KIND_CHOICE,
    ReverseFillAnswer,
    ReverseFillSampleRow,
    ReverseFillSpec,
)
from surveycore.core.task import ExecutionConfig, ExecutionState


class TestReverseFillRuntimeState:
    def _build_state(self) -> ExecutionState:
        spec = ReverseFillSpec(
            source_path="demo.xlsx",
            selected_format="wjx_sequence",
            detected_format="wjx_sequence",
            start_row=1,
            total_samples=2,
            available_samples=2,
            target_num=2,
            samples=[
                ReverseFillSampleRow(
                    data_row_number=1,
                    worksheet_row_number=2,
                    answers={
                        1: ReverseFillAnswer(
                            question_num=1,
                            kind=REVERSE_FILL_KIND_CHOICE,
                            choice_index=0,
                        )
                    },
                ),
                ReverseFillSampleRow(
                    data_row_number=2,
                    worksheet_row_number=3,
                    answers={
                        1: ReverseFillAnswer(
                            question_num=1,
                            kind=REVERSE_FILL_KIND_CHOICE,
                            choice_index=1,
                        )
                    },
                ),
            ],
        )
        state = ExecutionState(config=ExecutionConfig(reverse_fill_spec=spec, target_num=2))
        state.initialize_reverse_fill_runtime()
        return state

    def test_acquire_commit_and_requeue_reverse_fill_rows(self) -> None:
        state = self._build_state()
        first = state.acquire_reverse_fill_sample("Worker-1")
        second = state.acquire_reverse_fill_sample("Worker-2")

        assert first.status == "acquired"
        assert second.status == "acquired"
        assert first.sample and first.sample.data_row_number == 1
        assert second.sample and second.sample.data_row_number == 2
        assert state.commit_reverse_fill_sample("Worker-1") == 1
        assert state.mark_reverse_fill_submission_failed("Worker-2", max_retries=1) == (2, False)
        retried = state.acquire_reverse_fill_sample("Worker-2")
        assert retried.sample and retried.sample.data_row_number == 2

    def test_discarded_row_can_make_target_unreachable(self) -> None:
        state = self._build_state()
        state.acquire_reverse_fill_sample("Worker-1")
        state.commit_reverse_fill_sample("Worker-1")
        state.acquire_reverse_fill_sample("Worker-2")
        state.mark_reverse_fill_submission_failed("Worker-2", max_retries=1)
        state.acquire_reverse_fill_sample("Worker-2")

        assert state.mark_reverse_fill_submission_failed("Worker-2", max_retries=1) == (2, True)
        assert state.is_reverse_fill_target_unreachable()

    def test_acquire_returns_disabled_when_runtime_not_initialized(self) -> None:
        result = ExecutionState(config=ExecutionConfig()).acquire_reverse_fill_sample("Worker-1")
        assert result.status == "disabled"
        assert result.message == "reverse_fill_disabled"

    def test_release_without_requeue_drops_reserved_row(self) -> None:
        state = self._build_state()
        first = state.acquire_reverse_fill_sample("Worker-1")
        released_row = state.release_reverse_fill_sample("Worker-1", requeue=False)
        second = state.acquire_reverse_fill_sample("Worker-2")
        exhausted = state.acquire_reverse_fill_sample("Worker-3")

        assert first.sample and first.sample.data_row_number == 1
        assert released_row == 1
        assert second.sample and second.sample.data_row_number == 2
        assert exhausted.status == "exhausted"

    def test_get_reverse_fill_answer_uses_thread_reserved_sample(self) -> None:
        state = self._build_state()
        state.acquire_reverse_fill_sample("Worker-1")
        state.acquire_reverse_fill_sample("Worker-2")

        answer = state.get_reverse_fill_answer(1, "Worker-2")
        assert answer and answer.choice_index == 1
        assert state.get_reverse_fill_answer(1, "Worker-3") is None

    def test_resolve_current_reverse_fill_answer_filters_invalid_contexts(self) -> None:
        expected = ReverseFillAnswer(
            question_num=1,
            kind=REVERSE_FILL_KIND_CHOICE,
            choice_index=0,
        )

        class _ValidContext:
            def get_reverse_fill_answer(self, _question_num: int) -> ReverseFillAnswer:
                return expected

        class _BadValueContext:
            def get_reverse_fill_answer(self, _question_num: int) -> str:
                return "not-an-answer"

        class _ErrorContext:
            def get_reverse_fill_answer(self, _question_num: int) -> ReverseFillAnswer:
                raise RuntimeError("boom")

        assert resolve_current_reverse_fill_answer(_ValidContext(), 1) is expected
        assert resolve_current_reverse_fill_answer(_BadValueContext(), 1) is None
        assert resolve_current_reverse_fill_answer(_ErrorContext(), 1) is None
        assert resolve_current_reverse_fill_answer(object(), 1) is None
        assert resolve_current_reverse_fill_answer(None, 1) is None

    def test_resolve_current_reverse_fill_answer_uses_explicit_thread(self) -> None:
        expected = ReverseFillAnswer(
            question_num=1,
            kind=REVERSE_FILL_KIND_CHOICE,
            choice_index=1,
        )
        calls: list[tuple[int, str]] = []

        class _Context:
            def get_reverse_fill_answer(
                self,
                question_num: int,
                thread_name: str,
            ) -> ReverseFillAnswer:
                calls.append((question_num, thread_name))
                return expected

        assert (
            resolve_current_reverse_fill_answer(_Context(), 1, thread_name="Slot-2") is expected
        )
        assert calls == [(1, "Slot-2")]
