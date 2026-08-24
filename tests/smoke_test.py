from importlib import metadata

import surveycore

assert surveycore.__version__ == metadata.version("surveycore-py")
assert surveycore.SurveyClient
