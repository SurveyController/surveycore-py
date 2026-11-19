from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from surveycore.core.questions.meta_helpers import (
    count_positive_weights,
    find_all_zero_attached_selects,
    find_all_zero_matrix_rows,
)
from surveycore.core.questions.schema import QuestionEntry
from surveycore.providers.contracts import SurveyQuestionMeta, ensure_survey_question_meta

__all__ = ["validate_question_config"]


_TEXT_MIN_LENGTH_PATTERNS = (
    re.compile(r"(?:至少|最少|不少于|不低于)\s*(\d+)\s*(?:个)?(?:字|字符|汉字)"),
    re.compile(r"(\d+)\s*(?:个)?(?:字|字符|汉字)\s*(?:以上|起)"),
)


def _extract_text_min_length(*fragments: Any) -> Optional[int]:

    limits: List[int] = []
    for fragment in fragments:
        text = str(fragment or "").strip()
        if not text:
            continue
        for pattern in _TEXT_MIN_LENGTH_PATTERNS:
            for match in pattern.finditer(text):
                try:
                    limits.append(int(match.group(1)))
                except ValueError:
                    continue
    return max(limits) if limits else None


def _is_text_ai_enabled(entry: QuestionEntry) -> bool:
    question_type = str(entry.question_type or "").strip()
    if question_type == "text":
        return bool(entry.ai_enabled)
    if question_type == "multi_text":
        blank_flags = entry.multi_text_blank_ai_flags or []
        return bool(entry.ai_enabled) or (bool(blank_flags) and all(bool(flag) for flag in blank_flags))
    return False


def _text_answer_too_short_indexes(entry: QuestionEntry, min_length: int) -> List[tuple[int, int]]:
    issues: List[tuple[int, int]] = []
    for answer_index, raw_answer in enumerate((entry.texts or []), start=1):
        answer = str(raw_answer or "").strip()
        if len(answer) < min_length:
            issues.append((answer_index, len(answer)))
    return issues


def _text_random_mode_label(raw_mode: Any) -> str:
    mode = str(raw_mode or "").strip().lower()
    return {
        "name": "随机姓名",
        "mobile": "随机手机号",
        "id_card": "随机身份证号",
        "integer": "随机整数",
    }.get(mode, "随机处理")


def _display_question_num(raw_num: Any, question_info: Optional[SurveyQuestionMeta]) -> Any:
    if question_info is not None:
        display_num = getattr(question_info, "display_num", None)
        if display_num not in (None, ""):
            return display_num
    return raw_num


def _validate_text(entry: QuestionEntry, number: int | None, meta: SurveyQuestionMeta) -> str | None:
    if _is_text_ai_enabled(entry):
        return None
    minimum = _extract_text_min_length(meta.title, meta.description)
    if minimum is None or minimum <= 0:
        return None
    mode = str(entry.text_random_mode or "").strip().lower()
    if entry.question_type == "text" and mode not in ("", "none"):
        return (
            f"第 {number} 题（填空题）配置冲突：\n"
            f"  - 题目要求答案最少 {minimum} 字\n"
            f"  - 当前选择的是{_text_random_mode_label(mode)}，无法保证达到字数要求\n"
            "  - 请改用足够长的答案列表，或启用 AI 作答"
        )
    short_answers = _text_answer_too_short_indexes(entry, minimum)
    if not short_answers:
        return None
    detail = "、".join(
        f"第 {answer_index} 个答案 {length} 字" for answer_index, length in short_answers[:5]
    )
    if len(short_answers) > 5:
        detail += f" 等 {len(short_answers)} 个答案"
    return (
        f"第 {number} 题（填空题）配置冲突：\n"
        f"  - 题目要求答案最少 {minimum} 字\n"
        f"  - 但答案列表里 {detail}，达不到要求\n"
        "  - 请改长答案，或启用 AI 作答"
    )


def validate_question_config(
    entries: List[QuestionEntry],
    questions_info: Optional[List[SurveyQuestionMeta | Dict[str, Any]]] = None,
) -> Optional[str]:

    if not entries:
        return "未配置任何题目"

    errors: List[str] = []
    question_info_map: dict[int, SurveyQuestionMeta] = {}
    unsupported_questions: List[SurveyQuestionMeta] = []
    for item in questions_info or []:
        if not isinstance(item, (dict, SurveyQuestionMeta)):
            continue
        meta = ensure_survey_question_meta(item)
        if meta.num > 0:
            question_info_map[meta.num] = meta
        if bool(meta.unsupported):
            unsupported_questions.append(meta)

    if unsupported_questions:
        lines = ["当前问卷包含暂不支持的题型，已禁止启动："]
        for item in unsupported_questions[:12]:
            title = str(item.title or f"第{item.num}题").strip()
            provider_type = str(item.provider_type or item.type_code or "未知类型").strip()
            reason = str(item.unsupported_reason or "").strip()
            suffix = f"（{provider_type}，{reason}）" if reason else f"（{provider_type}）"
            lines.append(f"  - 第 {item.num} 题：{title}{suffix}")
        if len(unsupported_questions) > 12:
            lines.append(f"  - 其余 {len(unsupported_questions) - 12} 道暂不支持题目已省略")
        return "\n".join(lines)

    for idx, entry in enumerate(entries):
        question_num = entry.question_num
        question_type = entry.question_type
        try:
            normalized_question_num = idx + 1 if question_num is None else int(question_num)
        except (TypeError, ValueError, OverflowError):
            normalized_question_num = idx + 1

        question_info = question_info_map.get(normalized_question_num)
        display_question_num = _display_question_num(question_num, question_info)

        if question_type == "multiple":
            weights = entry.custom_weights or entry.probabilities
            if isinstance(weights, list):
                positive_count = count_positive_weights(weights)
                if positive_count <= 0:
                    errors.append(
                        f"第 {display_question_num} 题（多选题）配置无效：\n"
                        "  - 当前所有选项概率都小于等于 0%\n"
                        "  - 请至少将 1 个选项的概率设为大于 0%"
                    )
                    continue
                minimum = question_info.multi_min_limit if question_info is not None else None
                if minimum is not None and minimum > 0 and positive_count < minimum:
                    errors.append(
                        f"第 {display_question_num} 题（多选题）配置冲突：\n"
                        f"  - 题目要求最少选择 {minimum} 项\n"
                        f"  - 但只有 {positive_count} 个选项的概率大于 0%\n"
                        f"  - 请至少将 {minimum} 个选项的概率设为大于 0%"
                    )
        if question_type in ("text", "multi_text") and question_info is not None:
            text_error = _validate_text(entry, display_question_num, question_info)
            if text_error:
                errors.append(text_error)

        configured_weights = entry.probabilities
        if str(entry.distribution_mode or "").strip().lower() == "custom" and entry.custom_weights not in (None, []):
            configured_weights = entry.custom_weights
        if question_type in ("single", "dropdown", "scale", "score") and isinstance(configured_weights, list):
            if configured_weights and count_positive_weights(configured_weights) <= 0:
                errors.append(
                    f"第 {display_question_num} 题（{question_type}）配置无效：\n"
                    "  - 当前所有选项配比都小于等于 0\n"
                    "  - 请至少将 1 个选项的配比设为大于 0"
                )

        if question_type == "matrix":
            invalid_rows = find_all_zero_matrix_rows(configured_weights)
            if invalid_rows == [0]:
                errors.append(
                    f"第 {display_question_num} 题（矩阵题）配置无效：\n"
                    "  - 当前所有选项配比都小于等于 0\n"
                    "  - 请至少将 1 个选项的配比设为大于 0"
                )
            else:
                for row_idx in invalid_rows:
                    errors.append(
                        f"第 {display_question_num} 题（矩阵题）配置无效：\n"
                        f"  - 第 {row_idx} 行所有选项配比都小于等于 0\n"
                        "  - 请至少将 1 个选项的配比设为大于 0"
                    )

        for cfg_idx, option_text in find_all_zero_attached_selects(entry.attached_option_selects or []):
            errors.append(
                f"第 {display_question_num} 题（嵌入式下拉）配置无效：\n"
                f"  - 第 {cfg_idx} 组（{option_text or '未命名选项'}）所有配比都小于等于 0\n"
                "  - 请至少将 1 个选项的配比设为大于 0"
            )

    return "\n\n".join(errors) if errors else None
