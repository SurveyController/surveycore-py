from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, List, Optional

from surveycore.app.config import DEFAULT_FILL_TEXT, DIMENSION_UNGROUPED
from surveycore.core.psychometrics import JOINT_PSYCHOMETRIC_SUPPORTED_TYPES
from surveycore.core.psychometrics.ordinal_options import infer_ordinal_option_mapping
from surveycore.core.questions.meta_helpers import (
    count_positive_weights,
    find_all_zero_attached_selects,
    find_all_zero_matrix_rows,
)
from surveycore.core.questions.schema import (
    _TEXT_RANDOM_ID_CARD,
    _TEXT_RANDOM_ID_CARD_TOKEN,
    _TEXT_RANDOM_INTEGER,
    _TEXT_RANDOM_MOBILE,
    _TEXT_RANDOM_MOBILE_TOKEN,
    _TEXT_RANDOM_NAME,
    _TEXT_RANDOM_NAME_TOKEN,
    _TEXT_RANDOM_NONE,
    GLOBAL_RELIABILITY_DIMENSION,
    QuestionEntry,
    _infer_option_count,
)
from surveycore.core.questions.strict_ratio import is_strict_custom_ratio_mode
from surveycore.core.questions.utils import (
    build_random_int_token,
    normalize_option_fill_texts,
    normalize_probabilities,
    normalize_single_like_prob_config,
    resolve_prob_config,
    serialize_random_int_range,
    try_parse_random_int_range,
)
from surveycore.providers.common import make_provider_question_key

if TYPE_CHECKING:
    from surveycore.core.task import ExecutionConfig

__all__ = ["configure_probabilities"]

_TEXT_RANDOM_TOKENS = {
    _TEXT_RANDOM_NAME: _TEXT_RANDOM_NAME_TOKEN,
    _TEXT_RANDOM_MOBILE: _TEXT_RANDOM_MOBILE_TOKEN,
    _TEXT_RANDOM_ID_CARD: _TEXT_RANDOM_ID_CARD_TOKEN,
}


def _resolve_runtime_dimension(
    entry: QuestionEntry,
    *,
    reliability_mode_enabled: bool,
    strict_ratio: bool,
    allows_reliability: Optional[bool] = None,
) -> Optional[str]:
    allows_joint_ratio = (
        bool(allows_reliability)
        if allows_reliability is not None
        else entry.question_type.strip() in JOINT_PSYCHOMETRIC_SUPPORTED_TYPES
    )
    if not reliability_mode_enabled or (strict_ratio and not allows_joint_ratio):
        return None
    raw_dimension = str(entry.dimension or "").strip()
    if not raw_dimension or raw_dimension == DIMENSION_UNGROUPED:
        return None
    return raw_dimension


def _raise_if_all_zero_single_like(raw_weights: Any, question_num: int, question_type: str) -> None:
    if isinstance(raw_weights, list) and raw_weights and count_positive_weights(raw_weights) <= 0:
        raise ValueError(
            f"第 {question_num} 题（{question_type}）配置无效：所有选项配比均为 0，请至少保留一个大于 0 的选项。"
        )

def _raise_if_all_zero_matrix(raw_weights: Any, question_num: int) -> None:
    invalid_rows = find_all_zero_matrix_rows(raw_weights)
    if not invalid_rows:
        return
    if invalid_rows == [0]:
        raise ValueError(
            f"第 {question_num} 题（矩阵题）配置无效：所有选项配比均为 0，请至少保留一个大于 0 的选项。"
        )
    raise ValueError(
        f"第 {question_num} 题（矩阵题）配置无效：第 {invalid_rows[0]} 行配比全部为 0，请至少保留一个大于 0 的选项。"
    )

def _raise_if_all_zero_attached_selects(entry: QuestionEntry, question_num: int) -> None:
    issues = find_all_zero_attached_selects(entry.attached_option_selects or [])
    if not issues:
        return
    cfg_idx, option_text = issues[0]
    raise ValueError(
        f"第 {question_num} 题（嵌入式下拉）配置无效：第 {cfg_idx} 组（{option_text or '未命名选项'}）配比全部为 0，请至少保留一个大于 0 的选项。"
    )


def _normalize_matrix_row(raw_row: Any, option_count: int) -> list[float] | None:
    if not isinstance(raw_row, (list, tuple)):
        return None
    cleaned: list[float] = []
    for value in raw_row:
        try:
            cleaned.append(max(0.0, float(value)))
        except (TypeError, ValueError, OverflowError):
            continue
    if not cleaned:
        return None
    cleaned = cleaned[:option_count]
    cleaned.extend([1.0] * (option_count - len(cleaned)))
    try:
        return normalize_probabilities(cleaned)
    except ValueError:
        return None


def _matrix_weights(entry: QuestionEntry, probs: Any, rows: int) -> list[list[float] | int]:
    option_count = max(1, _infer_option_count(entry))
    for weights in (probs, entry.custom_weights):
        if isinstance(weights, list) and any(isinstance(row, (list, tuple)) for row in weights):
            normalized: list[list[float] | int] = []
            last_row = None
            for index in range(rows):
                raw_row = weights[index] if index < len(weights) else last_row
                row = _normalize_matrix_row(raw_row, option_count)
                normalized.append(row if row is not None else [1.0 / option_count] * option_count)
                if raw_row is not None:
                    last_row = raw_row
            return normalized
    if isinstance(probs, list):
        row = _normalize_matrix_row(probs, option_count)
        if row is None:
            row = [1.0 / option_count] * option_count
        return [row.copy() for _ in range(rows)]
    return [-1] * rows


def _slider_target(entry: QuestionEntry, probs: Any) -> float:
    if str(entry.distribution_mode or "").strip().lower() == "random":
        return float("nan")
    custom_weights = entry.custom_weights
    if isinstance(custom_weights, (list, tuple)) and custom_weights:
        first = custom_weights[0]
        if isinstance(first, (int, float)):
            try:
                return float(first)
            except OverflowError:
                pass
    if isinstance(probs, (int, float)):
        return float(probs)
    if isinstance(probs, list) and probs:
        try:
            return float(probs[0])
        except (TypeError, ValueError, OverflowError):
            pass
    return 50.0


def _configure_text(entry: QuestionEntry, probs: Any, ctx: ExecutionConfig) -> None:
    text_random_mode = str(entry.text_random_mode or _TEXT_RANDOM_NONE).strip().lower()
    normalized_values = [str(item).strip() for item in (entry.texts or []) if str(item).strip()]
    normalized_blank_ai_flags: List[bool] = []
    normalized_blank_int_ranges: List[List[int]] = []
    if entry.question_type == "multi_text":
        raw_blank_ai_flags = entry.multi_text_blank_ai_flags or []
        if isinstance(raw_blank_ai_flags, list):
            normalized_blank_ai_flags = [bool(flag) for flag in raw_blank_ai_flags]
        raw_blank_int_ranges = entry.multi_text_blank_int_ranges or []
        if isinstance(raw_blank_int_ranges, list):
            normalized_blank_int_ranges = [serialize_random_int_range(item) for item in raw_blank_int_ranges]
        for blank_idx, mode in enumerate(entry.multi_text_blank_modes or []):
            if str(mode or _TEXT_RANDOM_NONE).strip().lower() != _TEXT_RANDOM_INTEGER:
                continue
            target_range = raw_blank_int_ranges[blank_idx] if blank_idx < len(raw_blank_int_ranges) else []
            if try_parse_random_int_range(target_range) is None:
                raise ValueError(f"多项填空题第{blank_idx + 1}个空位的随机整数范围未设置完整")
    ai_enabled = bool(entry.ai_enabled) or (bool(normalized_blank_ai_flags) and all(normalized_blank_ai_flags))
    if entry.question_type == "text":
        random_token = _TEXT_RANDOM_TOKENS.get(text_random_mode)
        if text_random_mode == _TEXT_RANDOM_INTEGER:
            text_random_range = serialize_random_int_range(entry.text_random_int_range)
            if len(text_random_range) != 2:
                raise ValueError("填空题随机整数范围未设置完整")
            random_token = build_random_int_token(*text_random_range)
        if random_token is not None:
            ai_enabled = False
            normalized_values = [random_token]
    if not normalized_values:
        if ai_enabled:
            normalized_values = [DEFAULT_FILL_TEXT]
        else:
            raise ValueError("填空题至少需要一个候选答案")
    if isinstance(probs, list) and len(probs) == len(normalized_values):
        normalized = normalize_probabilities([float(value) for value in probs])
    else:
        normalized = normalize_probabilities([1.0] * len(normalized_values))
    ctx.texts.append(normalized_values)
    ctx.texts_prob.append(normalized)
    ctx.text_entry_types.append(entry.question_type)
    ctx.text_ai_flags.append(ai_enabled)
    ctx.text_titles.append(str(entry.question_title or ""))
    ctx.multi_text_blank_modes.append(entry.multi_text_blank_modes)
    ctx.multi_text_blank_ai_flags.append(normalized_blank_ai_flags)
    ctx.multi_text_blank_int_ranges.append(normalized_blank_int_ranges)


def _reset_question_config(ctx: ExecutionConfig) -> None:
    ctx.single_prob = []
    ctx.droplist_prob = []
    ctx.multiple_prob = []
    ctx.matrix_prob = []
    ctx.scale_prob = []
    ctx.slider_targets = []
    ctx.texts = []
    ctx.texts_prob = []
    ctx.text_entry_types = []
    ctx.text_ai_flags = []
    ctx.text_titles = []
    ctx.location_parts = {}
    ctx.multi_text_blank_modes = []
    ctx.multi_text_blank_ai_flags = []
    ctx.multi_text_blank_int_ranges = []
    ctx.single_option_fill_texts = []
    ctx.single_attached_option_selects = []
    ctx.droplist_option_fill_texts = []
    ctx.multiple_option_fill_texts = []
    ctx.question_config_index_map = {}
    ctx.provider_question_config_index_map = {}
    ctx.question_dimension_map = {}
    ctx.question_ordinal_score_map = {}
    ctx.question_strict_ratio_map = {}
    ctx.question_psycho_bias_map = {}


def configure_probabilities(
    entries: List[QuestionEntry],
    ctx: "ExecutionConfig",
    reliability_mode_enabled: bool = True,
) -> None:
    _reset_question_config(ctx)

    def register(entry: QuestionEntry, question_num: int, kind: str, index: int) -> None:
        slot = (kind, index)
        ctx.question_config_index_map[question_num] = slot
        provider_key = make_provider_question_key(
            entry.survey_provider, entry.provider_page_id, entry.provider_question_id,
        )
        if provider_key:
            ctx.provider_question_config_index_map[provider_key] = slot

    reliability_candidates: list[tuple[int, bool, str]] = []

    def record_reliability(
        entry: QuestionEntry, question_num: int, strict_ratio: bool, *, ordinal_single: bool = False,
    ) -> None:
        ctx.question_dimension_map[question_num] = _resolve_runtime_dimension(
            entry,
            reliability_mode_enabled=reliability_mode_enabled,
            strict_ratio=strict_ratio,
            allows_reliability=True if ordinal_single else None,
        )
        bias = entry.psycho_bias
        if entry.question_type == "matrix" and isinstance(bias, list):
            ctx.question_psycho_bias_map[question_num] = list(bias)
        else:
            ctx.question_psycho_bias_map[question_num] = str(bias or "custom")
        reliability_candidates.append((question_num, strict_ratio, entry.question_type))

    text_index = 0
    for index, entry in enumerate(entries, start=1):
        question_num = entry.question_num if entry.question_num is not None else index
        inferred_count = _infer_option_count(entry)
        if inferred_count:
            entry.option_count = inferred_count
        probs = resolve_prob_config(
            entry.probabilities, entry.custom_weights, prefer_custom=entry.distribution_mode == "custom",
        )
        _raise_if_all_zero_attached_selects(entry, question_num)
        strict_ratio = is_strict_custom_ratio_mode(entry.distribution_mode, probs, entry.custom_weights)
        ctx.question_strict_ratio_map[question_num] = strict_ratio
        kind = entry.question_type

        if kind == "single":
            _raise_if_all_zero_single_like(probs, question_num, kind)
            register(entry, question_num, kind, len(ctx.single_prob))
            meta = getattr(ctx, "questions_metadata", {}).get(question_num)
            ordinal = infer_ordinal_option_mapping(list(meta.option_texts or []) if meta is not None else [])
            if ordinal is not None and ordinal.option_count == max(1, entry.option_count):
                ctx.question_ordinal_score_map[question_num] = list(ordinal.score_by_choice_index)
                record_reliability(entry, question_num, strict_ratio, ordinal_single=True)
            ctx.single_prob.append(normalize_single_like_prob_config(probs, entry.option_count))
            ctx.single_option_fill_texts.append(normalize_option_fill_texts(entry.option_fill_texts, entry.option_count))
            ctx.single_attached_option_selects.append(copy.deepcopy(entry.attached_option_selects or []))
        elif kind == "dropdown":
            _raise_if_all_zero_single_like(probs, question_num, kind)
            register(entry, question_num, kind, len(ctx.droplist_prob))
            record_reliability(entry, question_num, strict_ratio)
            ctx.droplist_prob.append(normalize_single_like_prob_config(probs, entry.option_count))
            ctx.droplist_option_fill_texts.append(normalize_option_fill_texts(entry.option_fill_texts, entry.option_count))
        elif kind in ("scale", "score"):
            _raise_if_all_zero_single_like(probs, question_num, kind)
            register(entry, question_num, kind, len(ctx.scale_prob))
            record_reliability(entry, question_num, strict_ratio)
            ctx.scale_prob.append(normalize_single_like_prob_config(probs, entry.option_count))
        elif kind == "multiple":
            register(entry, question_num, kind, len(ctx.multiple_prob))
            if not isinstance(probs, list):
                raise ValueError("多选题必须提供概率列表，数值范围0-100")
            ctx.multiple_prob.append([float(value) for value in probs])
            ctx.multiple_option_fill_texts.append(normalize_option_fill_texts(entry.option_fill_texts, entry.option_count))
        elif kind == "matrix":
            _raise_if_all_zero_matrix(probs, question_num)
            register(entry, question_num, kind, len(ctx.matrix_prob))
            record_reliability(entry, question_num, strict_ratio)
            ctx.matrix_prob.extend(_matrix_weights(entry, probs, max(1, entry.rows)))
        elif kind == "slider":
            register(entry, question_num, kind, len(ctx.slider_targets))
            ctx.slider_targets.append(_slider_target(entry, probs))
        elif kind == "order":
            register(entry, question_num, kind, -1)
        elif kind in ("text", "multi_text"):
            if entry.is_location:
                register(entry, question_num, "location", -1)
                ctx.location_parts[question_num] = [str(item or "").strip() for item in (entry.location_parts or [])[:3]]
            else:
                register(entry, question_num, "text", text_index)
                text_index += 1
            _configure_text(entry, probs, ctx)

    if not reliability_mode_enabled or any(ctx.question_dimension_map.values()):
        return
    for question_num, strict_ratio, question_type in reliability_candidates:
        supports_joint_ratio = question_type.strip() in JOINT_PSYCHOMETRIC_SUPPORTED_TYPES
        if (strict_ratio and not supports_joint_ratio) or ctx.question_dimension_map.get(question_num):
            continue
        ctx.question_dimension_map[question_num] = GLOBAL_RELIABILITY_DIMENSION
