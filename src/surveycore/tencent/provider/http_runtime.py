from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from collections import OrderedDict
from typing import Any, Callable, Mapping, Optional

import surveycore.network.http as http_client
from surveycore.app.config import DEFAULT_HTTP_HEADERS, DEFAULT_USER_AGENT
from surveycore.core.ai.batch_runtime import assert_no_free_ai_placeholders_in_actions
from surveycore.core.modes.duration_control import sample_answer_duration_seconds
from surveycore.core.persona.context import record_answer
from surveycore.core.questions.distribution import record_pending_distribution_choice
from surveycore.core.task import ExecutionConfig, ExecutionState
from surveycore.core.user_agent import UserAgentProfile
from surveycore.providers.answering import AnswerAction
from surveycore.providers.answering.option_fill import option_fill_text_map
from surveycore.providers.answering.recording import record_answer_action
from surveycore.providers.common import SURVEY_PROVIDER_QQ
from surveycore.providers.contracts import SurveyQuestionMeta, ensure_survey_question_metas
from surveycore.providers.errors import SubmitProxyUnavailableError
from surveycore.providers.http_logic import build_http_logic_plan
from surveycore.providers.http_progress import update_http_submit_step
from surveycore.tencent.provider.answering_builders import build_answer_action
from surveycore.tencent.provider.parser import (
    _build_qq_api_headers,
    _build_qq_survey_page_url,
    _ensure_qq_api_ok,
    _extract_qq_identifiers,
    _qq_chained_paths,
    _qq_score_labels,
    _request_qq_api,
    _standardize_qq_questions,
)
from surveycore.tencent.provider.question_types import (
    QQ_QUESTION_TYPES,
    QqAnswerEncoding,
    qq_provider_type,
)


class QqSubmitResult:
    SUCCESS = "success"
    FAILED = "failed"


_QQ_SUBMIT_TIMEOUT_SECONDS = 30
_QQ_FILLBLANK_TOKEN_RE = re.compile(r"\{(fillblank-[^{}]+)\}", re.IGNORECASE)


def _proxy_arg(proxy_address: str | None) -> Any:
    proxy = str(proxy_address or "").strip()
    return proxy if proxy else {}


def _headers(page_url: str, user_agent: str | None = None) -> dict[str, str]:
    headers = _build_qq_api_headers(page_url)
    headers["User-Agent"] = str(user_agent or "").strip() or DEFAULT_USER_AGENT
    return headers


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _raw_questions_by_id(questions: list[Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in questions:
        if not isinstance(item, Mapping):
            continue
        question_id = str(item.get("id") or "").strip()
        if question_id:
            result[question_id] = item
    return result


def _normalize_match_text(raw: Any) -> str:
    return "".join(str(raw or "").split())


def _meaningful_type_code(question: SurveyQuestionMeta) -> str:
    type_code = str(getattr(question, "type_code", "") or "").strip()
    return "" if type_code in {"", "0"} else type_code


def _question_signature(question: SurveyQuestionMeta) -> tuple[str, str]:
    provider_type = str(getattr(question, "provider_type", "") or "").strip().lower()
    type_marker = provider_type or _meaningful_type_code(question)
    return type_marker, _normalize_match_text(getattr(question, "title", ""))


def _question_types_compatible(current: SurveyQuestionMeta, existing: SurveyQuestionMeta) -> bool:
    current_provider_type = str(getattr(current, "provider_type", "") or "").strip().lower()
    existing_provider_type = str(getattr(existing, "provider_type", "") or "").strip().lower()
    if current_provider_type and existing_provider_type:
        return current_provider_type == existing_provider_type
    current_type = _meaningful_type_code(current)
    existing_type = _meaningful_type_code(existing)
    if current_type and existing_type:
        return current_type == existing_type
    return True


def _merge_submit_question_meta(existing: SurveyQuestionMeta, current: SurveyQuestionMeta) -> SurveyQuestionMeta:
    merged = current.to_dict()
    merged["num"] = int(getattr(existing, "num", 0) or merged.get("num") or 0)
    merged["display_num"] = getattr(existing, "display_num", None)
    if not str(merged.get("title") or "").strip():
        merged["title"] = str(getattr(existing, "title", "") or "").strip()
    if not str(merged.get("description") or "").strip():
        merged["description"] = str(getattr(existing, "description", "") or "").strip()
    merged["has_jump"] = bool(getattr(existing, "has_jump", False))
    merged["jump_rules"] = list(getattr(existing, "jump_rules", []) or [])
    merged["has_display_condition"] = bool(getattr(existing, "has_display_condition", False))
    merged["display_conditions"] = list(getattr(existing, "display_conditions", []) or [])
    merged["has_dependent_display_logic"] = bool(getattr(existing, "has_dependent_display_logic", False))
    merged["controls_display_targets"] = list(getattr(existing, "controls_display_targets", []) or [])
    merged["logic_parse_status"] = str(getattr(existing, "logic_parse_status", "") or merged.get("logic_parse_status") or "")
    merged["question_media"] = list(getattr(existing, "question_media", []) or merged.get("question_media") or [])
    merged["required"] = bool(getattr(existing, "required", merged.get("required", False)))
    return ensure_survey_question_metas([merged], default_provider=SURVEY_PROVIDER_QQ)[0]


def _match_existing_submit_question(
    current: SurveyQuestionMeta,
    existing_by_signature: dict[tuple[str, str], list[SurveyQuestionMeta]],
    ordered_existing: list[SurveyQuestionMeta],
    index: int,
) -> Optional[SurveyQuestionMeta]:
    signature = _question_signature(current)
    if signature[1]:
        candidates = existing_by_signature.get(signature) or []
        if candidates:
            return candidates.pop(0)
    if index < len(ordered_existing):
        candidate = ordered_existing[index]
        if _question_types_compatible(current, candidate):
            return candidate
    return None


def _normalize_submit_questions(config: ExecutionConfig, raw_questions: list[Any]) -> list[SurveyQuestionMeta]:
    normalized_inputs = _standardize_qq_questions(
        [item for item in raw_questions if isinstance(item, Mapping)]
    )
    normalized_questions = ensure_survey_question_metas(
        normalized_inputs,
        default_provider=SURVEY_PROVIDER_QQ,
    )
    current_questions = [item for item in normalized_questions if not bool(getattr(item, "is_description", False))]
    ordered_existing = [
        item
        for _, item in sorted((config.questions_metadata or {}).items(), key=lambda pair: int(pair[0]))
        if not bool(getattr(item, "is_description", False))
    ]
    existing_by_signature: dict[tuple[str, str], list[SurveyQuestionMeta]] = {}
    for item in ordered_existing:
        signature = _question_signature(item)
        if signature[1]:
            existing_by_signature.setdefault(signature, []).append(item)

    merged_questions: list[SurveyQuestionMeta] = []
    for index, current in enumerate(current_questions):
        existing = _match_existing_submit_question(
            current,
            existing_by_signature,
            ordered_existing,
            index,
        )
        merged_questions.append(_merge_submit_question_meta(existing, current) if existing is not None else current)
    return merged_questions


def _option_items(raw_question: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    options = raw_question.get("options")
    if isinstance(options, list):
        return [item for item in options if isinstance(item, Mapping)]
    return []


def _extract_option_blank_id(value: Any, *, depth: int = 0) -> str:
    if depth > 4 or value is None:
        return ""
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key or "").strip()
            match = _QQ_FILLBLANK_TOKEN_RE.search(key_text)
            if match:
                return str(match.group(1) or "").strip()
            lowered_key = key_text.lower()
            if "fillblank" in lowered_key:
                raw_id = str(item or "").strip()
                return raw_id or "fillblank"
            nested = _extract_option_blank_id(item, depth=depth + 1)
            if nested:
                return nested
        return ""
    if isinstance(value, (list, tuple, set)):
        for item in value:
            nested = _extract_option_blank_id(item, depth=depth + 1)
            if nested:
                return nested
        return ""
    match = _QQ_FILLBLANK_TOKEN_RE.search(str(value or ""))
    return str(match.group(1) or "").strip() if match else ""


def _option_blank_answer(raw_option: Mapping[str, Any], fill_text: str) -> dict[str, str]:
    blank_id = _extract_option_blank_id(raw_option)
    if not blank_id:
        blank_id = str(raw_option.get("id") or "").strip()
    return {
        "id": blank_id,
        "value": str(fill_text or "").strip(),
    }


def _option_answer(raw_option: Mapping[str, Any], *, checked: bool) -> dict[str, Any]:
    return {
        "id": str(raw_option.get("id") or "").strip(),
        "text": str(raw_option.get("text") or "").strip(),
        "checked": 1 if checked else 0,
    }


def _score_question_answer(raw_question: Mapping[str, Any], action: AnswerAction) -> dict[str, Any]:
    scores = _qq_score_labels(raw_question)
    index = action.scalar_value
    if index is None and action.selected_indices:
        index = action.selected_indices[0]
    if index is None or not 0 <= index < len(scores):
        raise RuntimeError(f"腾讯问卷第{int(action.question_num or 0)}题没有生成评分答案")
    return {
        "id": str(raw_question.get("id") or action.question_id).strip(),
        "type": raw_question["type"],
        "text": scores[index],
    }


def _choice_question_answer(raw_question: Mapping[str, Any], action: AnswerAction) -> dict[str, Any]:
    selected = {int(item) for item in action.selected_indices}
    fill_by_index = option_fill_text_map(action.option_fill_texts)
    blanks: list[dict[str, str]] = []
    options: list[dict[str, Any]] = []
    for index, option in enumerate(_option_items(raw_question)):
        if index not in selected:
            continue
        options.append(_option_answer(option, checked=True))
        fill_text = fill_by_index.get(index, "")
        if not fill_text:
            continue
        blanks.append(_option_blank_answer(option, fill_text))
    return {
        "id": str(raw_question.get("id") or action.question_id).strip(),
        "type": raw_question["type"],
        "blanks": blanks,
        "options": options,
    }


def _text_question_answer(raw_question: Mapping[str, Any], action: AnswerAction) -> dict[str, Any]:
    text_values = [str(item or "").strip() for item in action.text_values if str(item or "").strip()]
    return {
        "id": str(raw_question.get("id") or action.question_id).strip(),
        "type": raw_question["type"],
        "text": "\n".join(text_values),
    }


def _matrix_question_answer(raw_question: Mapping[str, Any], action: AnswerAction) -> dict[str, Any]:
    rows = raw_question.get("sub_titles")
    question_id = str(raw_question.get("id") or action.question_id).strip()
    provider_type = qq_provider_type(raw_question)
    definition = QQ_QUESTION_TYPES.get(provider_type)
    encoding = definition.answer_encoding if definition else None
    label = f"腾讯问卷第{action.question_num}题"
    options = _option_items(raw_question) if encoding == "matrix_options" else []
    scores = _qq_score_labels(raw_question) if encoding == "matrix_score_text" else []
    if not options and not scores:
        raise RuntimeError(f"{label}没有可提交的矩阵列")
    if not isinstance(rows, list) or not rows or len(rows) != len(action.matrix_indices):
        raise RuntimeError(f"{label}没有生成完整的矩阵答案")

    groups: list[dict[str, Any]] = []
    for row_index, (row, index) in enumerate(zip(rows, action.matrix_indices, strict=True), 1):
        row_label = f"{label}第{row_index}行"
        if not isinstance(row, Mapping) or not isinstance(row.get("id"), str) or not row["id"].strip():
            raise RuntimeError(f"{row_label}缺少矩阵行 id")
        if not 0 <= index < (len(options) or len(scores)):
            raise RuntimeError(f"{row_label}没有生成矩阵答案")
        if options:
            option = _option_answer(options[index], checked=True)
            if not option["id"]:
                raise RuntimeError(f"{row_label}缺少矩阵列 id")
            groups.append({"id": row["id"], "options": [option]})
        else:
            groups.append({"id": row["id"], "text": scores[index]})
    return {"id": question_id, "type": raw_question["type"], "groups": groups}


def _chained_question_answer(raw_question: Mapping[str, Any], action: AnswerAction) -> dict[str, Any]:
    paths = _qq_chained_paths(raw_question)
    if len(action.selected_indices) != 1 or not 0 <= action.selected_indices[0] < len(paths):
        raise RuntimeError(f"腾讯问卷第{action.question_num}题没有生成有效的联动选项路径")
    ids, texts = paths[action.selected_indices[0]]
    return {
        "id": str(raw_question.get("id") or action.question_id).strip(),
        "type": raw_question["type"],
        "id_list": list(ids),
        "text_list": list(texts),
    }


_ANSWER_ENCODERS: dict[QqAnswerEncoding, Callable[[Mapping[str, Any], AnswerAction], dict[str, Any]]] = {
    "choice_options": _choice_question_answer,
    "text": _text_question_answer,
    "score_text": _score_question_answer,
    "matrix_options": _matrix_question_answer,
    "matrix_score_text": _matrix_question_answer,
    "chained_path": _chained_question_answer,
}


def _question_answer(raw_question: Mapping[str, Any], action: AnswerAction) -> dict[str, Any]:
    provider_type = qq_provider_type(raw_question)
    if not provider_type:
        raise RuntimeError(f"腾讯问卷第{action.question_num}题缺少腾讯题型 type")
    definition = QQ_QUESTION_TYPES.get(provider_type)
    if definition is None or definition.answer_encoding is None:
        raise RuntimeError(f"腾讯问卷第{action.question_num}题没有可用的提交编码：{provider_type}")
    return _ANSWER_ENCODERS[definition.answer_encoding](raw_question, action)


def _record_action(ctx: ExecutionState, action: AnswerAction, thread_name: str = "") -> None:
    record_answer_action(
        ctx,
        action,
        record_answer_fn=record_answer,
        record_pending_distribution_choice_fn=record_pending_distribution_choice,
        default_fill_text="",
        thread_name=thread_name,
    )


async def _fetch_submit_source(
    survey_id: str,
    hash_value: str,
    *,
    headers: dict[str, str],
    proxies: Any,
) -> tuple[str, dict[str, Any], list[Any]]:
    session_payload = await _request_qq_api(survey_id, "session", hash_value=hash_value, headers=headers, proxies=proxies)
    session_data = _ensure_qq_api_ok(session_payload, "session")
    answer_session_id = str(session_data.get("answer_session_id") or "").strip()
    if answer_session_id:
        headers["X-Answer-Session"] = answer_session_id

    questions_payload = await _request_qq_api(
        survey_id,
        "questions",
        hash_value=hash_value,
        headers=headers,
        extra_params={"locale": "zhs"},
        proxies=proxies,
    )
    questions_data = _ensure_qq_api_ok(questions_payload, "questions")
    raw_questions = questions_data.get("questions")
    if not isinstance(raw_questions, list) or not raw_questions:
        raise RuntimeError("腾讯问卷题目接口未返回可提交题目")
    return answer_session_id, session_data, raw_questions


def _submit_response_answer_hash(payload: Mapping[str, Any]) -> str:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return ""
    return str(data.get("answer_hash") or "").strip()


def _extract_answer_session_state(session_data: Mapping[str, Any]) -> tuple[int, int]:
    answer_session = session_data.get("answer_session")
    if not isinstance(answer_session, Mapping):
        return 0, 0
    last_submitted_at = _safe_int(answer_session.get("last_submitted_at"))
    last_answer_id = _safe_int(answer_session.get("last_answer_id"))
    return last_submitted_at, last_answer_id


async def _confirm_qq_submit_persisted(
    survey_id: str,
    hash_value: str,
    *,
    headers: dict[str, str],
    proxies: Any,
    answer_session_id: str,
    initial_session_data: Mapping[str, Any],
    submit_payload: Mapping[str, Any],
) -> None:
    answer_hash = _submit_response_answer_hash(submit_payload)
    if not answer_hash:
        raise RuntimeError("腾讯问卷提交返回缺少 answer_hash，无法确认服务端是否已收录")
    if not answer_session_id:
        return

    initial_submitted_at, initial_answer_id = _extract_answer_session_state(initial_session_data)
    verify_headers = dict(headers)
    verify_headers["X-Answer-Session"] = answer_session_id
    for attempt in range(3):
        session_payload = await _request_qq_api(
            survey_id,
            "session",
            hash_value=hash_value,
            headers=verify_headers,
            proxies=proxies,
        )
        session_data = _ensure_qq_api_ok(session_payload, "session")
        last_submitted_at, last_answer_id = _extract_answer_session_state(session_data)
        if last_submitted_at > initial_submitted_at:
            return
        if last_answer_id > 0 and last_answer_id != initial_answer_id:
            return
        if attempt < 2:
            await asyncio.sleep(0.2)
    raise RuntimeError("腾讯问卷提交后未确认到服务端已记录答案")


def classify_qq_submit_payload(payload: Mapping[str, Any]) -> str:
    code = str(payload.get("code") or "").upper()
    if code in {"OK", "0"}:
        return QqSubmitResult.SUCCESS
    return QqSubmitResult.FAILED


def _raise_qq_submit_failed(payload: Mapping[str, Any]) -> None:
    message = str(payload.get("message") or payload.get("msg") or payload.get("code") or payload).strip()
    raise RuntimeError(f"腾讯问卷提交失败：{message}")


async def brush_qq_http(
    config: ExecutionConfig,
    ctx: ExecutionState,
    *,
    stop_signal: Any = None,
    thread_name: str = "",
    psycho_plan: Any = None,
    proxy_address: str | None = None,
    user_agent: str | None = None,
    user_agent_profile: UserAgentProfile | None = None,
    submit_proxy_lease_factory: Any = None,
) -> bool:
    _ = user_agent_profile
    if stop_signal is not None and stop_signal.is_set():
        return False
    try:
        survey_id, hash_value = _extract_qq_identifiers(config.url)
        page_url = _build_qq_survey_page_url(survey_id, hash_value)
        headers = _headers(page_url, user_agent)
        answer_session_id, session_data, raw_questions = await _fetch_submit_source(
            survey_id,
            hash_value,
            headers=headers,
            proxies={},
        )

        raw_by_id = _raw_questions_by_id(raw_questions)
        questions = _normalize_submit_questions(config, raw_questions)

        await update_http_submit_step(ctx, thread_name, "生成答案")
        for question in questions:
            if stop_signal is not None and stop_signal.is_set():
                return False
            if bool(getattr(question, "unsupported", False)):
                raise RuntimeError(f"腾讯问卷第{question.num}题暂不支持：{question.unsupported_reason or question.type_code}")

        async def _build_action(question: SurveyQuestionMeta) -> AnswerAction | None:
            if stop_signal is not None and stop_signal.is_set():
                return None
            action = await build_answer_action(
                None,
                question,
                ctx,
                psycho_plan=psycho_plan,
                thread_name=thread_name,
                allow_ai_placeholder=False,
            )
            if action is not None:
                _record_action(ctx, action, thread_name)
            return action

        plan = await build_http_logic_plan(
            questions,
            build_action=_build_action,
        )
        actions = list(plan.actions)
        assert_no_free_ai_placeholders_in_actions(actions, provider_label="腾讯问卷")
        action_by_question_id = {
            str(action.question_id or "").strip(): action
            for action in actions
            if str(action.question_id or "").strip()
        }
        if not action_by_question_id:
            raise RuntimeError("腾讯问卷没有生成可提交答案")

        page_questions: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        for raw_question in raw_questions:
            if stop_signal is not None and stop_signal.is_set():
                return False
            question_id = str(raw_question.get("id") or "").strip() if isinstance(raw_question, Mapping) else ""
            if not question_id:
                continue
            action = action_by_question_id.get(question_id)
            if action is None:
                continue
            raw_source = raw_by_id.get(question_id, raw_question)
            page_id = str((raw_source.get("page_id") if isinstance(raw_source, Mapping) else "") or "").strip()
            if not page_id:
                raise RuntimeError(f"腾讯问卷第{int(action.question_num or 0)}题缺少 page_id")
            question_answer = _question_answer(raw_source, action)
            page_questions.setdefault(page_id, []).append(question_answer)

        if not page_questions:
            raise RuntimeError("腾讯问卷没有生成可提交答案")

        try:
            duration = int(
                sample_answer_duration_seconds(
                    config.answer_duration_range_seconds,
                    survey_provider="qq",
                    default_unconfigured_seconds=90,
                )
                or 90
            )
        except Exception:
            duration = 90
        duration = max(1, duration)
        user_agent_value = str(user_agent or "").strip() or DEFAULT_USER_AGENT
        submit_body = {
            "survey_id": int(survey_id),
            "hash": hash_value,
            "answer_survey": {
                "duration": duration,
                "ua": user_agent_value,
                "referrer": "",
                "uid": str(uuid.uuid4()),
                "sid": str(uuid.uuid4()),
                "openid": "",
                "latitude": None,
                "longitude": None,
                "is_update": False,
                "locale": "zhs",
                "pages": [
                    {
                        "id": page_id,
                        "questions": questions_on_page,
                    }
                    for page_id, questions_on_page in page_questions.items()
                ],
            },
        }
        if not bool(getattr(config, "submit_enabled", True)):
            logging.info("腾讯问卷 HTTP 单测已生成答案，未提交。")
            return True

        submit_headers = {
            **DEFAULT_HTTP_HEADERS,
            "User-Agent": user_agent_value,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://wj.qq.com",
            "Referer": page_url,
        }
        if answer_session_id:
            submit_headers["X-Answer-Session"] = answer_session_id
        await update_http_submit_step(ctx, thread_name, "提交问卷")
        submit_proxy_address = str(proxy_address or "").strip() or None
        submit_proxy_lease = None
        if submit_proxy_lease_factory is not None:
            submit_proxy_lease = await submit_proxy_lease_factory()
            submit_proxy_address = str(getattr(submit_proxy_lease, "address", "") or "").strip() or None
        if stop_signal is not None and stop_signal.is_set():
            return False
        if bool(getattr(config, "random_proxy_ip_enabled", False)) and not submit_proxy_address:
            raise SubmitProxyUnavailableError("提交前未获取到随机 IP")
        submit_proxies = _proxy_arg(submit_proxy_address)
        try:
            response = await http_client.apost(
                f"https://wj.qq.com/api/v2/respondent/surveys/{survey_id}/answers",
                params={"pv_uid": str(uuid.uuid4()), "hash": hash_value, "_": str(int(time.time() * 1000))},
                json=submit_body,
                headers=submit_headers,
                timeout=_QQ_SUBMIT_TIMEOUT_SECONDS,
                proxies=submit_proxies,
            )
            response.raise_for_status()
        except Exception:
            raise
        await update_http_submit_step(ctx, thread_name, "校验结果")
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("腾讯问卷提交返回了非 JSON 对象")
        if classify_qq_submit_payload(payload) != QqSubmitResult.SUCCESS:
            _raise_qq_submit_failed(payload)
        await _confirm_qq_submit_persisted(
            survey_id,
            hash_value,
            headers=headers,
            proxies={},
            answer_session_id=answer_session_id,
            initial_session_data=session_data,
            submit_payload=payload,
        )
        return True
    finally:
        ctx.clear_free_ai_prefill_answers(thread_name)


__all__ = ["QqSubmitResult", "brush_qq_http", "classify_qq_submit_payload"]
