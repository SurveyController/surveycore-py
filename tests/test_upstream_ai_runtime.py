from __future__ import annotations

from types import SimpleNamespace

import pytest

from surveycore.core.ai import batch_runtime, runtime
from surveycore.core.task import ExecutionConfig, ExecutionState
from surveycore.providers.answering import AnswerAction
from surveycore.providers.contracts import SurveyQuestionMeta


def test_build_ai_prompts_normalizes_number_and_description() -> None:
    assert runtime.build_ai_question_prompt(" * 12、职业", description="限十字") == (
        "职业\n补充说明：限十字"
    )
    assert runtime.build_ai_question_prompt("", question_number=3) == "第3题"
    assert runtime.build_ai_option_fill_prompt(
        question_title="1. 其他",
        question_number=1,
        option_text=" 自定义 ",
    ) == "其他\n当前选择项：自定义"


@pytest.mark.asyncio
async def test_generate_ai_answer_supports_sync_async_and_multiple_values() -> None:
    sync_ctx = SimpleNamespace(
        config=SimpleNamespace(answer_generator=lambda *_args, **_kwargs: " 文本答案 ")
    )

    async def async_generator(*_args, **_kwargs):
        return "甲||乙"

    async_ctx = SimpleNamespace(config=SimpleNamespace(answer_generator=async_generator))

    assert await runtime.agenerate_ai_answer("题目", ctx=sync_ctx) == "文本答案"
    assert await runtime.agenerate_ai_answer(
        "题目",
        question_type="multi_fill_blank",
        blank_count=2,
        ctx=async_ctx,
    ) == ["甲", "乙"]


@pytest.mark.asyncio
async def test_generate_ai_answer_rejects_invalid_generators() -> None:
    with pytest.raises(runtime.AIRuntimeError, match="注入生成器"):
        await runtime.agenerate_ai_answer("题目", ctx=SimpleNamespace(config=SimpleNamespace()))

    empty_ctx = SimpleNamespace(
        config=SimpleNamespace(answer_generator=lambda *_args, **_kwargs: "")
    )
    with pytest.raises(runtime.AIRuntimeError, match="空内容"):
        await runtime.agenerate_ai_answer("题目", ctx=empty_ctx)

    mismatch_ctx = SimpleNamespace(
        config=SimpleNamespace(answer_generator=lambda *_args, **_kwargs: "只有一个")
    )
    with pytest.raises(runtime.AIRuntimeError, match="期望 2 项"):
        await runtime.agenerate_ai_answer(
            "题目",
            question_type="multi_fill_blank",
            blank_count=2,
            ctx=mismatch_ctx,
        )


@pytest.mark.asyncio
async def test_prefill_ai_answers_keeps_thread_scoped_result() -> None:
    config = ExecutionConfig()
    config.answer_generator = lambda *_args, **_kwargs: "上海||羽毛球"
    config.questions_metadata = {
        1: SurveyQuestionMeta(num=1, title="城市和爱好", text_inputs=2),
    }
    state = ExecutionState(config=config)
    action = AnswerAction(
        question_num=1,
        kind="text",
        text_values=(
            runtime.build_free_ai_text_placeholder(1, 0),
            runtime.build_free_ai_text_placeholder(1, 1),
        ),
    )

    await batch_runtime.prefill_free_ai_answers_for_questions(
        list(config.questions_metadata.values()),
        [action],
        state,
        thread_name="slot-1",
    )

    assert state.get_free_ai_prefill_answer("slot-1", 1) == ("上海", "羽毛球")


def test_assert_no_ai_placeholders_checks_text_and_option_fill() -> None:
    text_action = AnswerAction(
        question_num=1,
        kind="text",
        text_values=(runtime.build_free_ai_text_placeholder(1, 0),),
    )
    option_action = AnswerAction(
        question_num=2,
        kind="choice",
        option_fill_texts=((0, runtime.build_free_ai_option_fill_placeholder(2, 0)),),
    )

    with pytest.raises(runtime.AIRuntimeError, match="问卷星"):
        batch_runtime.assert_no_free_ai_placeholders_in_actions(
            [text_action],
            provider_label="问卷星",
        )
    with pytest.raises(runtime.AIRuntimeError, match="未处理"):
        batch_runtime.assert_no_free_ai_placeholders_in_actions([option_action])
