from importlib.metadata import version as _distribution_version

from .client import SurveyClient
from .config import deserialize_config, dumps_config, loads_config, serialize_config
from .errors import (
    ConfigError,
    SubmissionError,
    SurveyCoreError,
    SurveyParseError,
    SurveyUnavailableError,
    UnsupportedSurveyError,
)
from .models import (
    AnswerGenerator,
    QuestionConfig,
    RunConfig,
    SubmissionRequest,
    SubmissionResult,
    SurveyDefinition,
    SurveyQuestion,
)

__version__ = _distribution_version("surveycore-py")

__all__ = [
    "AnswerGenerator",
    "ConfigError",
    "QuestionConfig",
    "RunConfig",
    "SubmissionError",
    "SubmissionRequest",
    "SubmissionResult",
    "SurveyClient",
    "SurveyCoreError",
    "SurveyDefinition",
    "SurveyParseError",
    "SurveyQuestion",
    "SurveyUnavailableError",
    "UnsupportedSurveyError",
    "deserialize_config",
    "dumps_config",
    "loads_config",
    "serialize_config",
]
