from types import SimpleNamespace

import pytest

from surveycore.core.task import ExecutionConfig, ExecutionState
from surveycore.credamo.provider import answering_builders as credamo_builders
from surveycore.providers.contracts import SurveyQuestionMeta
from surveycore.tencent.provider import answering_builders as qq_builders
from surveycore.wjx.provider import answering_builders as wjx_builders


def _state(provider: str, entry_type: str, **config_values) -> ExecutionState:
    config = ExecutionConfig(survey_provider=provider)
    config.question_config_index_map = {1: (entry_type, 0)}
    for name, value in config_values.items():
        setattr(config, name, value)
    return ExecutionState(config=config)


@pytest.mark.asyncio
async def test_wjx_choice_dropdown_and_score_builders_honor_forced_choices() -> None:
    single = await wjx_builders.build_answer_action(
        None,
        SurveyQuestionMeta(
            num=1,
            title="单选",
            type_code="3",
            options=3,
            option_texts=["甲", "乙", "丙"],
            forced_option_index=2,
        ),
        _state("wjx", "single", single_prob=[-1], single_option_fill_texts=[None]),
        psycho_plan=None,
    )
    dropdown = await wjx_builders.build_answer_action(
        None,
        SurveyQuestionMeta(
            num=1,
            title="下拉",
            type_code="7",
            options=2,
            option_texts=["甲", "乙"],
            forced_option_index=1,
        ),
        _state("wjx", "dropdown", droplist_prob=[-1], droplist_option_fill_texts=[None]),
        psycho_plan=None,
    )
    score = await wjx_builders.build_answer_action(
        None,
        SurveyQuestionMeta(
            num=1,
            title="评分",
            type_code="5",
            options=5,
            option_texts=["1", "2", "3", "4", "5"],
            forced_option_index=3,
        ),
        _state("wjx", "score", scale_prob=[-1]),
        psycho_plan=None,
    )

    assert single is not None and single.selected_indices == (2,)
    assert single.selected_texts == ("丙",)
    assert dropdown is not None and dropdown.selected_indices == (1,)
    assert dropdown.record_type == "dropdown"
    assert score is not None and score.selected_indices == (3,)
    assert score.record_type == "score"


@pytest.mark.asyncio
async def test_wjx_text_builders_cover_static_and_ai_placeholder_paths() -> None:
    static_action = await wjx_builders.build_answer_action(
        None,
        SurveyQuestionMeta(num=1, title="两项填空", type_code="1", text_inputs=2),
        _state(
            "wjx",
            "multi_text",
            texts=[["固定答案"]],
            texts_prob=[[1.0]],
            text_ai_flags=[False],
            text_entry_types=["multi_text"],
            multi_text_blank_modes=[[]],
            multi_text_blank_int_ranges=[[]],
        ),
        psycho_plan=None,
    )
    placeholder_action = await wjx_builders.build_answer_action(
        None,
        SurveyQuestionMeta(num=1, title="AI 填空", type_code="1", text_inputs=2),
        _state(
            "wjx",
            "text",
            texts=[["备用"]],
            texts_prob=[[1.0]],
            text_ai_flags=[True],
        ),
        psycho_plan=None,
        allow_ai_placeholder=True,
    )

    assert static_action is not None and static_action.text_values == ("固定答案", "固定答案")
    assert placeholder_action is not None
    assert placeholder_action.text_values == ("__FREE_AI_TEXT__1_0", "__FREE_AI_TEXT__1_1")


@pytest.mark.asyncio
async def test_wjx_multiple_builders_cover_random_and_weighted_selection(monkeypatch) -> None:
    monkeypatch.setattr(wjx_builders.random, "randint", lambda low, high: high)
    monkeypatch.setattr(wjx_builders.random, "sample", lambda population, count: population[:count])
    random_action = await wjx_builders.build_answer_action(
        None,
        SurveyQuestionMeta(
            num=1,
            title="随机多选",
            type_code="4",
            options=4,
            option_texts=["甲", "乙", "丙", "丁"],
            multi_min_limit=2,
            multi_max_limit=2,
        ),
        _state("wjx", "multiple", multiple_prob=[[-1]], multiple_option_fill_texts=[None]),
        psycho_plan=None,
    )

    monkeypatch.setattr(wjx_builders.random, "random", lambda: 0.0)
    weighted_action = await wjx_builders.build_answer_action(
        None,
        SurveyQuestionMeta(
            num=1,
            title="权重多选",
            type_code="4",
            options=3,
            option_texts=["甲", "乙", "丙"],
            multi_min_limit=1,
            multi_max_limit=2,
        ),
        _state(
            "wjx",
            "multiple",
            multiple_prob=[[100.0, "bad", float("nan")]],
            multiple_option_fill_texts=[None],
        ),
        psycho_plan=None,
    )

    assert random_action is not None and random_action.selected_indices == (0, 1)
    assert weighted_action is not None and weighted_action.selected_indices == (0,)


@pytest.mark.asyncio
async def test_wjx_matrix_slider_order_and_unsupported_dispatch(monkeypatch) -> None:
    monkeypatch.setattr(
        wjx_builders,
        "get_tendency_index",
        lambda _count, _probs, **kwargs: int(kwargs.get("row_index") or 0),
    )
    matrix = await wjx_builders.build_answer_action(
        None,
        SurveyQuestionMeta(num=1, title="矩阵", type_code="6", rows=2, options=3),
        _state("wjx", "matrix", matrix_prob=[[1, 0, 0], [0, 1, 0]]),
        psycho_plan=None,
    )
    invalid_slider = await wjx_builders.build_answer_action(
        None,
        SurveyQuestionMeta(num=1, title="滑块", type_code="8"),
        _state("wjx", "slider", slider_targets=["invalid"]),
        psycho_plan=None,
    )
    monkeypatch.setattr(wjx_builders.random, "shuffle", lambda values: values.reverse())
    order = await wjx_builders.build_answer_action(
        None,
        SurveyQuestionMeta(
            num=1,
            title="排序",
            type_code="11",
            options=3,
            option_texts=["甲", "乙", "丙"],
        ),
        _state("wjx", "order"),
        psycho_plan=None,
    )
    location = await wjx_builders.build_answer_action(
        None,
        SurveyQuestionMeta(num=1, title="位置"),
        _state("wjx", "location"),
        psycho_plan=None,
    )

    assert matrix is not None and matrix.matrix_indices == (0, 1)
    assert len(matrix.pending_distribution_choices) == 2
    assert invalid_slider is not None and invalid_slider.slider_value == 50.0
    assert order is not None and order.selected_indices == (2, 1, 0)
    assert order.selected_texts == ("丙", "乙", "甲")
    assert location is None


@pytest.mark.asyncio
async def test_qq_builders_cover_all_supported_question_kinds(monkeypatch) -> None:
    monkeypatch.setattr(qq_builders, "weighted_index", lambda probabilities: probabilities.index(max(probabilities)))
    monkeypatch.setattr(qq_builders, "get_tendency_index", lambda *_args, **kwargs: int(kwargs.get("row_index") or 1))
    monkeypatch.setattr(qq_builders.random, "random", lambda: 0.0)

    cases = [
        (
            "single",
            SurveyQuestionMeta(num=1, title="单选", provider_question_id="q1", options=2, option_texts=["甲", "乙"]),
            {"single_prob": [[0, 1]], "single_option_fill_texts": [None]},
        ),
        (
            "dropdown",
            SurveyQuestionMeta(num=1, title="下拉", provider_question_id="q1", options=2, option_texts=["甲", "乙"]),
            {"droplist_prob": [[1, 0]], "droplist_option_fill_texts": [None]},
        ),
        (
            "text",
            SurveyQuestionMeta(num=1, title="填空", provider_question_id="q1", text_inputs=2),
            {"texts": [["答案"]], "texts_prob": [[1]], "text_ai_flags": [False]},
        ),
        (
            "score",
            SurveyQuestionMeta(num=1, title="评分", provider_question_id="q1", options=5),
            {"scale_prob": [[0, 0, 1, 0, 0]]},
        ),
        (
            "multiple",
            SurveyQuestionMeta(
                num=1,
                title="多选",
                provider_question_id="q1",
                options=3,
                option_texts=["甲", "乙", "丙"],
                multi_min_limit=1,
                multi_max_limit=2,
            ),
            {"multiple_prob": [[100, 0, 100]], "multiple_option_fill_texts": [None]},
        ),
        (
            "matrix",
            SurveyQuestionMeta(num=1, title="矩阵", provider_question_id="q1", rows=2, options=3),
            {"matrix_prob": [[1, 0, 0], [0, 1, 0]]},
        ),
    ]

    actions = []
    for entry_type, question, values in cases:
        actions.append(
            await qq_builders.build_answer_action(
                None,
                question,
                _state("qq", entry_type, **values),
                psycho_plan=None,
            )
        )

    assert [action.kind if action else None for action in actions] == [
        "choice",
        "select",
        "text",
        "choice",
        "choice",
        "matrix",
    ]
    assert actions[0] is not None and actions[0].selected_indices == (1,)
    assert actions[1] is not None and actions[1].selected_indices == (0,)
    assert actions[2] is not None and actions[2].text_values == ("答案", "答案")
    assert actions[3] is not None and actions[3].selected_indices == (1,)
    assert actions[4] is not None and actions[4].selected_indices == (0, 2)
    assert actions[5] is not None and actions[5].matrix_indices == (1, 1)


@pytest.mark.asyncio
async def test_qq_builder_rejects_incomplete_metadata_and_unknown_mapping() -> None:
    missing_id = await qq_builders.build_answer_action(
        None,
        SurveyQuestionMeta(num=1, title="缺少 ID", options=2),
        _state("qq", "single", single_prob=[-1], single_option_fill_texts=[None]),
        psycho_plan=None,
    )
    missing_mapping = await qq_builders.build_answer_action(
        None,
        SurveyQuestionMeta(num=1, title="缺少映射", provider_question_id="q1", options=2),
        ExecutionState(config=ExecutionConfig(survey_provider="qq")),
        psycho_plan=None,
    )
    unknown = await qq_builders.build_answer_action(
        None,
        SurveyQuestionMeta(num=1, title="未知类型", provider_question_id="q1", options=2),
        _state("qq", "order"),
        psycho_plan=None,
    )

    assert missing_id is None
    assert missing_mapping is None
    assert unknown is None


def test_credamo_builder_covers_supported_question_kinds(monkeypatch) -> None:
    config = ExecutionConfig(survey_provider="credamo")
    config.single_prob = [[0, 1, 0]]
    config.single_option_fill_texts = [None]
    config.multiple_prob = [[1, 0, 2]]
    config.multiple_option_fill_texts = [None]
    config.droplist_prob = [[1, 0, 0]]
    config.droplist_option_fill_texts = [None]
    config.scale_prob = [[0, 0, 1]]
    config.matrix_prob = [[1, 0, 0], [0, 1, 0]]
    config.texts = [["固定文本"]]
    config.texts_prob = [[1]]
    monkeypatch.setattr(credamo_builders, "weighted_index", lambda probabilities: probabilities.index(max(probabilities)))
    monkeypatch.setattr(credamo_builders.random, "shuffle", lambda values: values.reverse())

    metadata = SurveyQuestionMeta(num=1, title="题目", options=3, rows=2, text_inputs=2)
    actions = {
        kind: credamo_builders.build_answer_action(
            root_index=index,
            question_num=1,
            entry_type=kind,
            config_index=0,
            config=config,
            question_meta=metadata,
        )
        for index, kind in enumerate(
            ["single", "multiple", "dropdown", "scale", "matrix", "order", "multi_text"]
        )
    }

    assert actions["single"] is not None and actions["single"].selected_indices == (1,)
    assert actions["multiple"] is not None and actions["multiple"].selected_indices == (0, 2)
    assert actions["dropdown"] is not None and actions["dropdown"].selected_indices == (0,)
    assert actions["scale"] is not None and actions["scale"].selected_indices == (2,)
    assert actions["matrix"] is not None and actions["matrix"].matrix_indices == (0, 1)
    assert actions["order"] is not None and actions["order"].selected_indices == (2, 1, 0)
    assert actions["multi_text"] is not None
    assert actions["multi_text"].text_values == ("固定文本", "固定文本")


def test_credamo_builder_plan_and_invalid_inputs() -> None:
    class Plan:
        def get_choice(self, question_num, row_index):
            assert question_num == 1
            return 2 if row_index is None else row_index

    config = ExecutionConfig(survey_provider="credamo")
    config.single_prob = [[1, 0, 0]]
    config.single_option_fill_texts = [None]
    config.multiple_prob = [[0, 0, 0]]
    config.multiple_option_fill_texts = [None]

    planned = credamo_builders.build_answer_action(
        root_index=0,
        question_num=1,
        entry_type="single",
        config_index=0,
        config=config,
        question_meta=SurveyQuestionMeta(num=1, title="计划单选", options=3),
        psycho_plan=Plan(),
    )
    no_options = credamo_builders.build_answer_action(
        root_index=0,
        question_num=1,
        entry_type="single",
        config_index=0,
        config=config,
        question_meta=SimpleNamespace(options=0),
    )
    no_multiple = credamo_builders.build_answer_action(
        root_index=0,
        question_num=1,
        entry_type="multiple",
        config_index=0,
        config=config,
        question_meta=SurveyQuestionMeta(num=1, title="空多选", options=3),
    )
    unknown = credamo_builders.build_answer_action(
        root_index=0,
        question_num=1,
        entry_type="unknown",
        config_index=0,
        config=config,
        question_meta=SurveyQuestionMeta(num=1, title="未知", options=3),
    )

    assert planned is not None and planned.selected_indices == (2,)
    assert no_options is None
    assert no_multiple is None
    assert unknown is None
