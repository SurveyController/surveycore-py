from __future__ import annotations

import inspect
import re
from typing import Any, List, Optional


class AIRuntimeError(RuntimeError):
    pass


def build_ai_question_prompt(question_title: str, *, description: str = "", question_number: int = 0) -> str:
    title = re.sub(r"^\s*\*?\s*\d+[.、]?\s*", "", str(question_title or "").strip())
    if not title:
        title = f"第{int(question_number)}题" if int(question_number or 0) > 0 else ""
    description = str(description or "").strip()
    return f"{title}\n补充说明：{description}" if title and description else title


def build_ai_option_fill_prompt(*, question_title: str, question_number: int, option_text: str = "") -> str:
    prompt = build_ai_question_prompt(question_title, question_number=question_number)
    return f"{prompt}\n当前选择项：{str(option_text or '').strip()}".strip()


def build_free_ai_text_placeholder(question_num: int, blank_index: int) -> str:
    return f"__FREE_AI_TEXT__{int(question_num)}_{int(blank_index)}"


def build_free_ai_option_fill_placeholder(question_num: int, option_index: int) -> str:
    return f"__FREE_AI_OPTION_FILL__{int(question_num)}_{int(option_index)}"


def is_free_ai_text_placeholder(value: object) -> bool:
    return str(value or "").startswith("__FREE_AI_TEXT__")


def is_free_ai_option_fill_placeholder(value: object) -> bool:
    return str(value or "").startswith("__FREE_AI_OPTION_FILL__")


async def agenerate_ai_answer(
    question_title: str,
    *,
    question_type: str = "fill_blank",
    blank_count: Optional[int] = None,
    description: str = "",
    question_number: int = 0,
    ctx: Any = None,
) -> str | List[str]:
    callback = getattr(getattr(ctx, "config", None), "answer_generator", None)
    if not callable(callback):
        raise AIRuntimeError("文本题需要通过 answer_generator 注入生成器")
    prompt = build_ai_question_prompt(
        question_title,
        description=description,
        question_number=question_number,
    )
    try:
        value = callback(prompt, question_type=question_type, blank_count=blank_count, question_number=question_number)
        if inspect.isawaitable(value):
            value = await value
    except Exception as exc:
        raise AIRuntimeError(f"答案生成器调用失败：{exc}") from exc
    if question_type == "multi_fill_blank":
        values = value if isinstance(value, list) else [part.strip() for part in str(value or "").split("||")]
        values = [str(item or "").strip() for item in values if str(item or "").strip()]
        if blank_count and len(values) != int(blank_count):
            raise AIRuntimeError(f"答案生成器返回 {len(values)} 项，期望 {int(blank_count)} 项")
        if not values:
            raise AIRuntimeError("答案生成器返回空内容")
        return values
    text = str(value or "").strip()
    if not text:
        raise AIRuntimeError("答案生成器返回空内容")
    return text

