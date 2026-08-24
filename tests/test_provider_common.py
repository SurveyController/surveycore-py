import pytest

from surveycore.providers.common import (
    detect_survey_provider,
    ensure_question_provider_fields,
    make_provider_question_key,
    normalize_survey_parse_url,
)


@pytest.mark.parametrize(
    ("url", "provider"),
    [
        ("wjx.cn/vj/example.aspx", "wjx"),
        ("https://wj.qq.com/s1/123/abc", "qq"),
        ("https://www.credamo.com/s/example_", "credamo"),
    ],
)
def test_supported_provider_detection(url: str, provider: str) -> None:
    assert detect_survey_provider(url, default="") == provider


def test_provider_url_and_question_key_normalization() -> None:
    assert normalize_survey_parse_url("wjx.cn/vj/example.aspx") == "https://wjx.cn/vj/example.aspx"
    assert normalize_survey_parse_url("https://www.credamo.com/s/example_") == (
        "https://www.credamo.com/answer.html#/s/example_"
    )
    assert make_provider_question_key("QQ", "page-1", "q-2") == "qq:page-1:q-2"
    assert make_provider_question_key("qq", "", "q-2") == ""


def test_malicious_host_is_not_detected() -> None:
    assert detect_survey_provider("https://wjx.cn.evil.example/vj/example.aspx", default="") == ""


def test_question_provider_fields_are_normalized_without_mutating_input() -> None:
    raw = {"provider": "QQ", "provider_question_id": 12, "unsupported": 1}
    normalized = ensure_question_provider_fields(raw)

    assert raw == {"provider": "QQ", "provider_question_id": 12, "unsupported": 1}
    assert normalized["provider"] == "qq"
    assert normalized["provider_question_id"] == "12"
    assert normalized["unsupported"] is True
