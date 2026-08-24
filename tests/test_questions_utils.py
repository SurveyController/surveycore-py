import re
from types import SimpleNamespace
from typing import Any, cast

import pytest

from surveycore.core.questions import utils


def test_question_type_and_probability_helpers(monkeypatch) -> None:
    assert utils._normalize_question_type_code(None) == ""
    assert utils._normalize_question_type_code(" 3 ") == "3"
    assert utils._should_treat_question_as_text_like("1", 0, 1)
    assert not utils._should_treat_question_as_text_like("3", 0, 1)
    assert not utils._should_treat_question_as_text_like("1", 0, 1, is_location=True)
    assert not utils._should_treat_question_as_text_like("1", 0, 1, has_slider_matrix=True)
    assert utils._should_treat_question_as_text_like("unknown", 1, 2)

    monkeypatch.setattr(utils.random, "random", lambda: 0.6)
    assert utils.weighted_index([0, 1, 3]) == 2
    monkeypatch.setattr(utils.random, "randrange", lambda length: length - 1)
    assert utils.weighted_index(cast(Any, [float("nan"), -1, "bad"])) == 2
    with pytest.raises(ValueError, match="empty"):
        utils.weighted_index([])

    assert utils.normalize_probabilities([1, 3]) == [0.25, 0.75]
    with pytest.raises(ValueError, match="不能为空"):
        utils.normalize_probabilities([])
    with pytest.raises(ValueError, match="大于0"):
        utils.normalize_probabilities([0, 0])


def test_random_identity_values_are_structurally_valid(monkeypatch) -> None:
    monkeypatch.setattr(utils.random, "choice", lambda values: values[0])
    monkeypatch.setattr(utils.random, "random", lambda: 0.0)
    monkeypatch.setattr(utils.random, "randint", lambda low, _high: low)

    name = utils.generate_random_chinese_name()
    mobile = utils.generate_random_mobile()
    generic = utils.generate_random_generic_text()
    identity = utils.generate_random_id_card()

    assert len(name) == 2
    assert re.fullmatch(r"130\d{8}", mobile)
    assert generic == "已填写10"
    assert re.fullmatch(r"\d{17}[0-9X]", identity)
    assert identity[-1] == utils._calculate_id_card_checksum(identity[:17])
    assert len(utils._load_id_card_area_codes()) > 0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"min": "9", "max": 3}, (3, 9)),
        ([2, 5], (2, 5)),
        (("7", "7", "ignored"), (7, 7)),
        ({"min": "", "max": 3}, None),
        ("1,2", None),
    ],
)
def test_random_integer_range_contract(raw, expected) -> None:
    assert utils.try_parse_random_int_range(raw) == expected


def test_random_integer_tokens_and_descriptions(monkeypatch) -> None:
    assert utils.normalize_random_int_range([9, 3]) == (3, 9)
    assert utils.serialize_random_int_range({"min": 2, "max": 4}) == [2, 4]
    assert utils.serialize_random_int_range(None) == []
    assert utils.describe_random_int_range([4, 2]) == "2-4"
    assert utils.describe_random_int_range(None) == "未设置"
    assert utils.build_random_int_token(9, 3) == "__RANDOM_INT__:3:9"
    assert utils.parse_random_int_token(" __RANDOM_INT__:3:9 ") == (3, 9)
    assert utils.parse_random_int_token("__RANDOM_INT__:3") is None
    assert utils.parse_random_int_token("plain") is None
    assert utils.parse_random_int_token(None) is None
    with pytest.raises(ValueError, match="范围无效"):
        utils.normalize_random_int_range("invalid")

    monkeypatch.setattr(utils.random, "randint", lambda low, high: high)
    assert utils.generate_random_integer_text(3, 9) == "9"
    assert utils.resolve_dynamic_text_token("__RANDOM_INT__:3:9") == "9"
    assert utils.resolve_dynamic_text_token("  固定文本  ") == "固定文本"
    assert utils.resolve_dynamic_text_token("") == "无"
    assert utils.resolve_dynamic_text_token(None) == "无"


def test_dynamic_text_dispatches_to_each_generator(monkeypatch) -> None:
    monkeypatch.setattr(utils, "generate_random_chinese_name", lambda: "张三")
    monkeypatch.setattr(utils, "generate_random_mobile", lambda: "13000000000")
    monkeypatch.setattr(utils, "generate_random_id_card", lambda: "110101200001010010")
    monkeypatch.setattr(utils, "generate_random_generic_text", lambda: "随机文本")

    assert utils.resolve_dynamic_text_token("__RANDOM_NAME__") == "张三"
    assert utils.resolve_dynamic_text_token("__RANDOM_MOBILE__") == "13000000000"
    assert utils.resolve_dynamic_text_token("__RANDOM_ID_CARD__") == "110101200001010010"
    assert utils.resolve_dynamic_text_token("__RANDOM_TEXT__") == "随机文本"


def test_element_text_and_option_fill_normalization() -> None:
    assert utils.extract_text_from_element(SimpleNamespace(text="  可见文本  ")) == "可见文本"

    class AttributeOnly:
        text = ""

        @staticmethod
        def get_attribute(name):
            assert name == "textContent"
            return "  属性文本  "

    class Broken:
        @property
        def text(self):
            raise RuntimeError("broken")

        @staticmethod
        def get_attribute(_name):
            raise RuntimeError("broken")

    assert utils.extract_text_from_element(AttributeOnly()) == "属性文本"
    assert utils.extract_text_from_element(Broken()) == ""
    assert utils.get_fill_text_from_config([None, " 补充 "], 1) == "补充"
    assert utils.get_fill_text_from_config([None], 2) is None
    assert utils.get_fill_text_from_config(None, 0) is None

    assert utils.normalize_option_fill_texts([" 甲 ", None], 3) == ["甲", None, None]
    assert utils.normalize_option_fill_texts(["", None], 2) is None
    assert utils.normalize_option_fill_texts(None, 2) is None


def test_probability_config_normalization_and_custom_weight_precedence() -> None:
    assert utils.normalize_single_like_prob_config(-1, 3) == -1
    assert utils.normalize_droplist_probs(None, 2) == [0.5, 0.5]
    assert utils.normalize_droplist_probs([1, 3, 100], 2) == [0.25, 0.75]
    assert utils.normalize_droplist_probs([1], 2) == [1.0, 0.0]
    assert utils.normalize_droplist_probs([0, 0], 2) == [0.5, 0.5]
    assert utils.normalize_droplist_probs(cast(Any, "bad"), 2) == [0.5, 0.5]
    assert utils.normalize_droplist_probs([1], 0) == []

    custom = [[0, 2], [3, 0]]
    assert utils.resolve_prob_config([], custom, prefer_custom=True) == custom
    assert utils.resolve_prob_config([1, 0], custom, prefer_custom=True) == [1, 0]
    assert utils.resolve_prob_config(None, custom, prefer_custom=False) is None
    assert utils.resolve_prob_config(None, [[0], ["bad"]], prefer_custom=True) is None
