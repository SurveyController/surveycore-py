from html import escape
from urllib.parse import parse_qs, quote

import httpx
import pytest

from surveycore import RunConfig, SubmissionRequest, SurveyClient, SurveyParseError
from surveycore._question_metas import to_question_metas
from surveycore.core.questions.default_builder import build_default_question_entries
from surveycore.core.reverse_fill.schema import ReverseFillAnswer
from surveycore.core.task import ExecutionConfig, ExecutionState
from surveycore.providers.contracts import ensure_survey_question_metas
from surveycore.wjx.provider.answering_builders import build_answer_action
from surveycore.wjx.provider.html_parser import parse_survey_questions_from_html
from surveycore.wjx.provider.http_runtime import _submitdata_from_actions
from surveycore.wjx.provider.multilevel import parse_multilevel_options

_LEVEL_DATA = """华南地区
华北地区|---华南地区
湖南省
广东省
---华北地区
河北省
山东省|---湖南省
长沙市
株洲市
---广东省
广州市
深圳市
---河北省
石家庄市
保定区
---山东省
济南市
青岛市|---长沙市
天心区
岳麓区
---株洲市
荷塘区
芦淞区
---广州市
天河区
白云区
---深圳市
罗湖区
龙华区
---石家庄市
长安区
新华区
---保定区
竞秀区
莲池区
---济南市
历下区
章丘区
---青岛市
黄岛区
崂山区〒大区|省份|城市|区县"""
_MENU_HTML = f'<input id="hfLevelData" value="{escape(_LEVEL_DATA, quote=True)}">'
_PAGE_HTML = """
<html><head><title>多级下拉样本 - 问卷星</title></head><body>
<div id="divQuestion"><fieldset>
""" + "".join(
    f'<div topic="{num}" type="1"><input id="q{num}" type="text"></div>'
    for num in range(1, 11)
) + """
<div topic="11" id="div11" type="9" gapfill="1" relation="0" style="display:none;">
  <div class="field-label"><div class="topicnumber">11.</div><div class="topichtml">题目</div></div>
</div>
<div topic="12" id="div12" type="1" req="1">
  <div class="field-label"><div class="topicnumber">11.</div><div class="topichtml">请选择：</div></div>
  <input type="text" id="q12" verify="多级下拉" readonly="readonly"
    onclick="openCityBox(this,5,event,12);">
</div>
</fieldset></div>
<script>function DecodeId(input) { return input ^ 2130030173; }
var activityId = DecodeId(1797297031);</script>
</body></html>
"""


def test_multilevel_paths_follow_parents_and_use_wjx_separator() -> None:
    options = parse_multilevel_options(_MENU_HTML)
    assert len(options["option_texts"]) == 16
    assert options["option_texts"][0] == "华南地区‐湖南省‐长沙市‐天心区"
    assert options["option_texts"][-1] == "华北地区‐山东省‐青岛市‐崂山区"
    assert "华南地区‐河北省‐长沙市‐天心区" not in options["option_texts"]
    assert options["submit_values"] == options["option_texts"]
    assert options["level_labels"] == ["大区", "省份", "城市", "区县"]


def test_multilevel_preserves_submission_markers_and_decodes_cid_data() -> None:
    data = "总部╰1╯┌|---总部╰1╯┌\n研发部〒公司|部门"
    options = parse_multilevel_options(
        f'<input id="hfLevelData" value="{quote(data)}">', encoded=True
    )
    assert options["option_texts"] == ["总部‐研发部"]
    assert options["submit_values"] == ["总部┌‐研发部"]


def test_multilevel_stops_at_hidden_child_levels() -> None:
    data = "甲\n乙|---甲\n无下级々\n---乙\n分部|---无下级々\n占位々\n---分部\n研发部"
    options = parse_multilevel_options(f'<input id="hfLevelData" value="{data}">')
    assert options["submit_values"] == ["甲", "乙‐分部‐研发部"]


@pytest.mark.parametrize(
    ("html", "message"),
    [
        ("<html></html>", "hfLevelData"),
        ('<input id="hfLevelData" value="">', "层级数据为空"),
        ('<input id="hfLevelData" value="甲|---乙\n子项">', "父选项不存在"),
        ('<input id="hfLevelData" value="甲|---甲">', "缺少子选项"),
        (_MENU_HTML + '<script>var levelDataExternalUrl = "https://example.test/data";</script>', "外部数据源"),
    ],
)
def test_invalid_multilevel_data_is_rejected(html: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_multilevel_options(html)


@pytest.mark.asyncio
@pytest.mark.parametrize("encoded_activity_id", [False, True])
async def test_multilevel_parse_config_and_answer_pipeline(encoded_activity_id: bool) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/joinnew/setmenuselnew.aspx":
            assert dict(request.url.params) == {"activityid": "366296538", "ct": "5", "pos": "12"}
            assert request.headers["Referer"] == "https://v.wjx.cn/vm/sample.aspx"
            return httpx.Response(200, text=_MENU_HTML)
        html = _PAGE_HTML if encoded_activity_id else _PAGE_HTML.replace(
            "DecodeId(1797297031)", "366296538"
        )
        return httpx.Response(200, text=html)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = SurveyClient(http_client)
        survey = await client.parse("https://v.wjx.cn/vm/sample.aspx")
        question = survey.questions[-1]
        assert len(survey.questions) == 11
        assert question.num == 12 and question.display_num == 11
        assert question.type_code == "7"
        assert question.provider_type == "multilevel_dropdown"
        assert not question.is_location and not question.is_text_like
        assert question.text_inputs == 0
        assert question.options == 16
        assert len(requests) == 2
        assert not http_client.is_closed
        metas = to_question_metas(survey.questions)
        entries = build_default_question_entries(metas)
        assert entries[-1].question_type == "dropdown"
        execution = client._execution_config(
            RunConfig(url=survey.url, reliability_mode=False), survey
        )
        execution.droplist_prob = [[0.0] * 15 + [1.0]]
        action = await build_answer_action(
            None, metas[-1], ExecutionState(config=execution), psycho_plan=None
        )

    assert action is not None
    assert action.selected_indices == (15,)
    assert action.record_type == "dropdown"
    assert _submitdata_from_actions([action]) == "12$华北地区‐山东省‐青岛市‐崂山区"


@pytest.mark.asyncio
async def test_multilevel_reverse_fill_submits_path_instead_of_index(monkeypatch) -> None:
    questions = parse_survey_questions_from_html(_PAGE_HTML)
    question = questions[-1]
    options = parse_multilevel_options(_MENU_HTML)
    question["option_texts"] = options["option_texts"]
    question["options"] = 16
    question["provider_page_raw"].update(options)
    meta = ensure_survey_question_metas([question])[-1]
    state = ExecutionState(config=ExecutionConfig(question_config_index_map={12: ("dropdown", 0)}))
    monkeypatch.setattr(
        state, "get_reverse_fill_answer",
        lambda *_args: ReverseFillAnswer(12, "choice", choice_index=0),
    )
    action = await build_answer_action(None, meta, state, psycho_plan=None)
    assert action is not None
    assert _submitdata_from_actions([action]) == "12$华南地区‐湖南省‐长沙市‐天心区"


@pytest.mark.asyncio
async def test_multilevel_http_failure_does_not_become_empty_options() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/joinnew/setmenuselnew.aspx":
            return httpx.Response(503)
        return httpx.Response(200, text=_PAGE_HTML)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(SurveyParseError, match="503"):
            await SurveyClient(http_client).parse("https://v.wjx.cn/vm/sample.aspx")


@pytest.mark.asyncio
async def test_multilevel_submission_preserves_empty_hidden_gapfill() -> None:
    submitted = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/joinnew/setmenuselnew.aspx":
            return httpx.Response(200, text=_MENU_HTML)
        if request.method == "POST":
            fields = parse_qs(request.content.decode())
            answers = dict(part.split("$", 1) for part in fields["submitdata"][0].split("}"))
            submitted.append(answers)
            assert set(answers) == {str(num) for num in range(1, 13)}
            assert answers["11"] == ""
            assert answers["12"] in parse_multilevel_options(_MENU_HTML)["submit_values"]
            return httpx.Response(200, text="10〒/wjx/join/complete.aspx")
        return httpx.Response(200, text=_PAGE_HTML)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = SurveyClient(http_client)
        url = "https://v.wjx.cn/vm/sample.aspx"
        survey = await client.parse(url)
        result = await client.submit(SubmissionRequest(
            config=RunConfig(url=url, reliability_mode=False), survey=survey
        ))
    assert result.success, result.error
    assert len(submitted) == 1
