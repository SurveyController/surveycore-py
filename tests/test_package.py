from importlib.metadata import version

import surveycore


def test_runtime_version_matches_distribution_metadata() -> None:
    assert surveycore.__version__ == version("surveycore-py")
