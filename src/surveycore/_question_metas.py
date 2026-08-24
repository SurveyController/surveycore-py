from __future__ import annotations

from collections.abc import Iterable

from .models import SurveyQuestion
from .providers.contracts import SurveyQuestionMeta


def to_question_metas(questions: Iterable[SurveyQuestion]) -> list[SurveyQuestionMeta]:
    return [
        SurveyQuestionMeta(
            num=int(question.num),
            title=str(question.title),
            type_code=str(question.type_code),
            options=int(question.options),
            rows=int(question.rows),
            option_texts=list(question.option_texts),
            row_texts=list(question.row_texts),
            page=int(question.page),
            provider_question_id=str(question.provider_question_id),
            provider_page_id=str(question.provider_page_id),
            required=bool(question.required),
            display_num=question.display_num,
            description=question.description,
            forced_option_index=question.forced_option_index,
            forced_option_text=question.forced_option_text,
            forced_texts=list(question.forced_texts),
            fillable_options=list(question.fillable_options),
            attached_option_selects=[dict(item) for item in question.attached_option_selects],
            has_attached_option_select=question.has_attached_option_select,
            rating_max=question.rating_max,
            text_inputs=question.text_inputs,
            text_input_labels=list(question.text_input_labels),
            is_multi_text=question.is_multi_text,
            question_media=[dict(item) for item in question.question_media],
            slider_min=question.slider_min,
            slider_max=question.slider_max,
            slider_step=question.slider_step,
            multi_min_limit=question.multi_min_limit,
            multi_max_limit=question.multi_max_limit,
            provider_type=question.provider_type,
            provider_page_raw=question.provider_page_raw,
            is_text_like=bool(question.is_text_like),
            is_location=bool(question.is_location),
            is_description=bool(question.is_description),
            is_rating=bool(question.is_rating),
            is_slider_matrix=bool(question.is_slider_matrix),
            has_jump=bool(question.has_jump),
            jump_rules=[dict(item) for item in question.jump_rules],
            has_display_condition=bool(question.has_display_condition),
            display_conditions=[dict(item) for item in question.display_conditions],
            has_dependent_display_logic=bool(question.has_dependent_display_logic),
            controls_display_targets=[dict(item) for item in question.controls_display_targets],
            logic_parse_status=str(question.logic_parse_status),
            unsupported=bool(question.unsupported),
            unsupported_reason=str(question.unsupported_reason),
        )
        for question in questions
    ]
