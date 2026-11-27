from dataclasses import dataclass
from typing import Any, Literal, Mapping

QqAnswerEncoding = Literal[
    "choice_options", "text", "score_text", "matrix_options", "matrix_score_text", "chained_path"
]


@dataclass(frozen=True, slots=True)
class QqQuestionType:
    type_code: str
    answer_encoding: QqAnswerEncoding | None
    default_score_start: int | None = None
    has_selection_limits: bool = False


QQ_QUESTION_TYPES = {
    "radio": QqQuestionType("3", "choice_options"),
    "checkbox": QqQuestionType("4", "choice_options", has_selection_limits=True),
    "select": QqQuestionType("7", "choice_options"),
    "text": QqQuestionType("1", "text"),
    "textarea": QqQuestionType("1", "text"),
    "nps": QqQuestionType("5", "score_text", default_score_start=0),
    "star": QqQuestionType("5", "score_text", default_score_start=1),
    "matrix_radio": QqQuestionType("6", "matrix_options"),
    "matrix_star": QqQuestionType("6", "matrix_score_text", default_score_start=1),
    "chained_selects": QqQuestionType("7", "chained_path"),
    "description": QqQuestionType("0", None),
}


def qq_provider_type(question: Mapping[str, Any]) -> str:
    value = question.get("type")
    return value if isinstance(value, str) and value.strip() else ""
