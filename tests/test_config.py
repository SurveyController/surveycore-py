import pytest

from surveycore import ConfigError, QuestionConfig, RunConfig
from surveycore.config import deserialize_config, dumps_config, loads_config, serialize_config


def test_config_round_trip_excludes_answer_generator() -> None:
    config = RunConfig(
        url="https://www.wjx.cn/vj/example.aspx",
        questions=[QuestionConfig(
            question_type="single",
            probabilities=[1, 0, 0],
            option_fill_texts=[["候选一", "候选二"], "固定答案", None],
        )],
        answer_generator=lambda *_args, **_kwargs: "answer",
    )
    payload = serialize_config(config)
    assert payload["schema_version"] == 1
    assert "answer_generator" not in payload
    assert "ai_enabled" not in payload["questions"][0]
    restored = loads_config(dumps_config(config))
    assert restored.url == config.url
    assert restored.questions == config.questions


@pytest.mark.parametrize("option_fill_texts", ["固定答案", [False], [["候选一", 2]]])
def test_config_rejects_invalid_option_fill_texts(option_fill_texts) -> None:
    payload = {
        "schema_version": 1,
        "url": "https://www.wjx.cn/vj/example.aspx",
        "questions": [{"question_type": "single", "option_fill_texts": option_fill_texts}],
    }
    with pytest.raises(ConfigError, match="option_fill_texts"):
        deserialize_config(payload)


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
