from __future__ import annotations

import copy
import logging
from collections.abc import Sequence
from typing import Any

from surveycore.app.config import DEFAULT_FILL_TEXT
from surveycore.core.questions.meta_helpers import (
    infer_question_entry_type,
    normalize_attached_option_selects,
    normalize_fillable_option_indices,
)
from surveycore.core.questions.schema import (
    _TEXT_RANDOM_ID_CARD,
    _TEXT_RANDOM_MOBILE,
    _TEXT_RANDOM_NAME,
    _TEXT_RANDOM_NONE,
    QuestionEntry,
)
from surveycore.core.questions.utils import normalize_option_fill_texts
from surveycore.providers.common import (
    SURVEY_PROVIDER_WJX,
    detect_survey_provider,
    normalize_survey_provider,
)
from surveycore.providers.contracts import SurveyQuestionInput

__all__ = ["build_default_question_entries"]


def _as_float(val: Any, default: float) -> float:
    try:
        return float(val)
    except (TypeError, ValueError, OverflowError):
        return default


def _normalize_question_num(raw: Any) -> int | None:
    try:
        if raw is None:
            return None
        return int(raw)
    except (TypeError, ValueError, OverflowError):
        return None


def _normalize_title(raw: Any) -> str:
    try:
        text = str(raw or "").strip()
    except Exception:
        return ""
    if not text:
        return ""
    return "".join(text.split())


def _normalize_provider_key(raw_provider: Any, raw_question_id: Any) -> tuple[str, str] | None:
    provider = normalize_survey_provider(raw_provider, default=SURVEY_PROVIDER_WJX)
    question_id = str(raw_question_id or "").strip()
    if not question_id:
        return None
    return provider, question_id


def _normalize_forced_option_index(raw: Any, option_count: int) -> int | None:
    try:
        idx = int(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    total = max(0, int(option_count or 0))
    if 0 <= idx < total:
        return idx
    return None


def _build_forced_single_weights(option_count: int, forced_index: int) -> list[float]:
    total = max(1, int(option_count or 1))
    return [1.0 if idx == forced_index else 0.0 for idx in range(total)]


def _infer_multi_text_blank_modes(q: SurveyQuestionInput, blank_count: int) -> list[str]:
    labels = [str(item or "").strip() for item in (q.get("text_input_labels") or [])]
    title = str(q.get("title") or "").strip()
    modes: list[str] = []
    for index in range(max(0, int(blank_count or 0))):
        text = labels[index] if index < len(labels) else ""
        if not text and blank_count <= 1:
            text = title
        normalized = "".join(str(text or "").split()).lower()
        if any(marker in normalized for marker in ("手机号", "手机号码", "手机", "电话", "联系电话", "联系方式")):
            modes.append(_TEXT_RANDOM_MOBILE)
        elif any(marker in normalized for marker in ("身份证", "证件号", "证件号码")):
            modes.append(_TEXT_RANDOM_ID_CARD)
        elif any(marker in normalized for marker in ("姓名", "名字", "联系人")):
            modes.append(_TEXT_RANDOM_NAME)
        else:
            modes.append(_TEXT_RANDOM_NONE)
    return modes


def _default_entry(
    question: SurveyQuestionInput, kind: str, option_count: int,
) -> QuestionEntry:
    entry = QuestionEntry(kind, -1, option_count=option_count)
    if kind == "score":
        entry.option_count = max(option_count, 2)
        entry.probabilities = [1.0] * entry.option_count
        entry.custom_weights = entry.probabilities.copy()
        entry.distribution_mode = "custom"
    elif kind == "multiple":
        entry.probabilities = [50.0] * option_count
    elif kind == "slider":
        minimum = _as_float(question.get("slider_min"), 0.0)
        raw_maximum = question.get("slider_max")
        maximum = _as_float(raw_maximum, 100.0 if raw_maximum is None else raw_maximum)
        if maximum <= minimum:
            maximum = minimum + 100.0
        midpoint = minimum + (maximum - minimum) / 2.0
        entry.probabilities = [midpoint]
        entry.custom_weights = [midpoint]
        entry.distribution_mode = "custom"
        entry.option_count = 1
    elif kind in ("text", "multi_text"):
        entry.probabilities = [1.0]
        entry.texts = [DEFAULT_FILL_TEXT]
        if kind == "multi_text":
            entry.multi_text_blank_modes = _infer_multi_text_blank_modes(question, int(question.get("text_inputs") or 0))
    return entry


def _reuse_entry(existing: QuestionEntry, option_count: int) -> QuestionEntry:
    kind = existing.question_type
    entry = QuestionEntry(
        kind,
        copy.deepcopy(existing.probabilities),
        texts=copy.deepcopy(existing.texts),
        option_count=option_count,
        distribution_mode=existing.distribution_mode or "random",
        custom_weights=copy.deepcopy(existing.custom_weights),
        location_parts=list(existing.location_parts or []),
    )
    if kind in ("text", "multi_text"):
        entry.ai_enabled = existing.ai_enabled
    if kind == "text":
        entry.text_random_mode = str(existing.text_random_mode or _TEXT_RANDOM_NONE)
        entry.text_random_int_range = copy.deepcopy(existing.text_random_int_range)
    elif kind == "multi_text":
        entry.multi_text_blank_modes = copy.deepcopy(existing.multi_text_blank_modes)
        entry.multi_text_blank_ai_flags = copy.deepcopy(existing.multi_text_blank_ai_flags)
        entry.multi_text_blank_int_ranges = copy.deepcopy(existing.multi_text_blank_int_ranges)
    return entry


def build_default_question_entries(
    questions_info: Sequence[SurveyQuestionInput],
    *,
    survey_url: str = "",
    existing_entries: list[QuestionEntry] | None = None,
) -> list[QuestionEntry]:
    existing_by_num: dict[int, QuestionEntry] = {}
    existing_by_title: dict[str, QuestionEntry] = {}
    existing_by_provider: dict[tuple[str, str], QuestionEntry] = {}
    for entry in existing_entries or ():
        number = _normalize_question_num(entry.question_num)
        if number is not None:
            existing_by_num.setdefault(number, entry)
        title = _normalize_title(entry.question_title)
        if title:
            existing_by_title.setdefault(title, entry)
        provider_key = _normalize_provider_key(entry.survey_provider, entry.provider_question_id)
        if provider_key:
            existing_by_provider.setdefault(provider_key, entry)

    def find_existing(
        kind: str, title: str, number: int | None, provider_key: tuple[str, str] | None,
    ) -> QuestionEntry | None:
        candidate = existing_by_provider.get(provider_key) if provider_key else None
        if candidate is not None and candidate.question_type == kind:
            return candidate
        candidate = existing_by_num.get(number) if number is not None else None
        if candidate is not None and candidate.question_type == kind:
            saved_title = _normalize_title(candidate.question_title)
            if not title or not saved_title or title == saved_title:
                return candidate
        candidate = existing_by_title.get(title)
        return candidate if candidate is not None and candidate.question_type == kind else None

    detected_provider = detect_survey_provider(survey_url)
    entries: list[QuestionEntry] = []
    for question in questions_info:
        if question.get("is_description") or question.get("unsupported"):
            continue

        kind = infer_question_entry_type(question)
        option_count = max(int(question.get("options") or 0), int(question.get("rating_max") or 0), 1)
        if kind in ("text", "multi_text"):
            option_count = max(option_count, int(question.get("text_inputs") or 0))
        forced_index = _normalize_forced_option_index(question.get("forced_option_index"), option_count)
        title = str(question.get("title") or "").strip()
        provider = normalize_survey_provider(question.get("provider"), default=detected_provider)
        question_id = str(question.get("provider_question_id") or "").strip()
        existing = find_existing(
            kind, _normalize_title(title), _normalize_question_num(question.get("num")),
            _normalize_provider_key(provider, question_id),
        )
        entry = (
            _reuse_entry(existing, option_count)
            if existing is not None
            else _default_entry(question, kind, option_count)
        )
        entry.question_num = question.get("num")
        entry.question_title = title or None
        entry.survey_provider = provider
        entry.provider_question_id = question_id or None
        entry.provider_page_id = str(question.get("provider_page_id") or "").strip() or None
        entry.rows = int(question.get("rows") or 1)
        entry.is_location = bool(question.get("is_location"))

        if forced_index is not None and kind in ("single", "dropdown", "scale", "score"):
            if kind == "score":
                entry.option_count = max(entry.option_count, 2)
            weights = _build_forced_single_weights(entry.option_count, forced_index)
            entry.probabilities = weights
            entry.custom_weights = weights.copy()
            entry.distribution_mode = "custom"
            logging.info(
                "题号%s检测到指定作答指令，已强制锁定为第%s项（%s）",
                question.get("num"),
                forced_index + 1,
                str(question.get("forced_option_text") or "").strip() or "无文本",
            )
        if kind in ("text", "multi_text"):
            raw_forced_texts = question.get("forced_texts")
            forced_texts = [
                text for item in (raw_forced_texts if isinstance(raw_forced_texts, list) else [])
                if (text := str(item or "").strip())
            ]
            if forced_texts:
                entry.texts = forced_texts
                logging.info("题号%s检测到指定填空内容，已自动填入固定答案", question.get("num"))

        entry.fillable_option_indices = []
        if kind in ("single", "multiple", "dropdown"):
            entry.fillable_option_indices = normalize_fillable_option_indices(
                question.get("fillable_options"),
                entry.option_count,
                existing.fillable_option_indices if existing is not None else None,
            )
            entry.option_fill_texts = normalize_option_fill_texts(
                existing.option_fill_texts if existing is not None else None,
                entry.option_count,
                fillable_indices=set(entry.fillable_option_indices),
            )
        if kind == "single":
            entry.attached_option_selects = normalize_attached_option_selects(
                question.get("attached_option_selects"),
                existing.attached_option_selects if existing is not None else None,
            )
        entries.append(entry)
    return entries
