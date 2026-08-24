class SurveyCoreError(Exception):
    """Base class for public surveycore errors."""


class ConfigError(SurveyCoreError, ValueError):
    pass


class UnsupportedSurveyError(SurveyCoreError, ValueError):
    pass


class SurveyParseError(SurveyCoreError):
    pass


class SurveyUnavailableError(SurveyCoreError):
    pass


class SubmissionError(SurveyCoreError):
    pass
