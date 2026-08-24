import pytest

from surveycore.providers.errors import SurveyPausedError, SurveyStoppedError
from surveycore.wjx.provider.html_parser import parse_survey_questions_from_html
from surveycore.wjx.provider.parser import _parse_wjx_html


def test_wjx_fixture_parses_supported_and_unknown_questions() -> None:
    html = """
    <html><head><title>测试问卷 - 问卷星</title></head><body>
      <div id="divQuestion"><fieldset>
        <div topic="1" id="div1" type="3">
          <div class="topichtml">1. 单选</div>
          <div class="ui-controlgroup"><div><span class="label">甲</span></div><div><span class="label">乙</span></div></div>
        </div>
        <div topic="2" id="div2" type="99">
          <div class="topichtml">2. 未知</div>
        </div>
      </fieldset></div>
    </body></html>
    """

    questions = parse_survey_questions_from_html(html)
    assert len(questions) == 2
    assert questions[0]["type_code"] == "3"
    assert questions[0]["option_texts"] == ["甲", "乙"]
    assert questions[1]["type_code"] == "99"

    parsed_questions, title = _parse_wjx_html(html)
    assert title == "测试问卷"
    assert len(parsed_questions) == 2


@pytest.mark.parametrize(
    "html",
    [
        "<html><body>问卷已暂停，不能填写</body></html>",
        "<html><body><div id='divWorkError'>此问卷处于停止状态，无法作答</div></body></html>",
    ],
)
def test_wjx_page_state_is_rejected(html: str) -> None:
    with pytest.raises((SurveyPausedError, SurveyStoppedError)):
        _parse_wjx_html(html)
