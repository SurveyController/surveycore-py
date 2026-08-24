import pytest

from surveycore import ConfigError, QuestionConfig, RunConfig
from surveycore.config import deserialize_config, dumps_config, loads_config, serialize_config


def test_config_round_trip_excludes_answer_generator() -> None:
    config = RunConfig(
        url="https://www.wjx.cn/vj/example.aspx",
        questions=[QuestionConfig(question_type="single", probabilities=[1, 0])],
        answer_generator=lambda *_args, **_kwargs: "answer",
    )
    payload = serialize_config(config)
    assert payload["schema_version"] == 1
    assert "answer_generator" not in payload
    assert "ai_enabled" not in payload["questions"][0]
    assert loads_config(dumps_config(config)).url == config.url


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": 2},
        {"schema_version": 1, "url": "x", "proxy_source": "none"},
        {"schema_version": 1, "url": "x", "target": "1"},
    ],
)
def test_invalid_config_is_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ConfigError):
        deserialize_config(payload)
