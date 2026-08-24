from __future__ import annotations

from typing import Any, Iterable

from .runtime import (
    AIRuntimeError,
    agenerate_ai_answer,
    is_free_ai_option_fill_placeholder,
    is_free_ai_text_placeholder,
)


async def prefill_free_ai_answers_for_questions(questions: Iterable[Any], actions: Iterable[Any], ctx: Any, *, thread_name: str = "") -> None:
    del questions
    for action in actions:
        if not any(is_free_ai_text_placeholder(item) for item in tuple(getattr(action, "text_values", ()) or ())):
            continue
        question = next((q for q in list(getattr(ctx.config, "questions_metadata", {}).values()) if int(getattr(q, "num", 0) or 0) == int(getattr(action, "question_num", 0) or 0)), None)
        if question is None:
            continue
        answer = await agenerate_ai_answer(str(getattr(question, "title", "")), question_type="multi_fill_blank" if len(action.text_values) > 1 else "fill_blank", blank_count=len(action.text_values), question_number=action.question_num, ctx=ctx)
        values = tuple(answer if isinstance(answer, list) else [answer])
        ctx.set_free_ai_prefill_answers(thread_name, {int(action.question_num): values})


def assert_no_free_ai_placeholders_in_actions(actions: Iterable[Any], *, provider_label: str = "问卷") -> None:
    for action in actions:
        text_values = tuple(getattr(action, "text_values", ()) or ())
        raw_option_fill_pairs: Any = getattr(action, "option_fill_texts", ()) or ()
        option_fill_values = tuple(
            pair[1]
            for pair in tuple(raw_option_fill_pairs)
            if isinstance(pair, (list, tuple)) and len(pair) >= 2
        )
        if any(
            is_free_ai_text_placeholder(item) or is_free_ai_option_fill_placeholder(item)
            for item in text_values + option_fill_values
        ):
            raise AIRuntimeError(f"{provider_label}存在未处理的答案生成占位符")


__all__ = ["AIRuntimeError", "assert_no_free_ai_placeholders_in_actions", "prefill_free_ai_answers_for_questions"]
