import httpx
import pytest

import surveycore.client as client_module
from surveycore import (
    QuestionConfig,
    RunConfig,
    SubmissionRequest,
    SubmissionResult,
    SurveyClient,
    SurveyDefinition,
    SurveyParseError,
    SurveyQuestion,
    SurveyUnavailableError,
    UnsupportedSurveyError,
)
from surveycore.providers.common import detect_survey_provider, normalize_survey_parse_url


def test_url_detection_and_normalization() -> None:
    assert detect_survey_provider("wjx.cn/vj/example.aspx", default="") == "wjx"
    assert detect_survey_provider("https://wj.qq.com/s1/123/abc", default="") == "qq"
    assert detect_survey_provider("https://www.credamo.com/s/example_", default="") == "credamo"
    assert normalize_survey_parse_url("wjx.cn/vj/example.aspx").startswith("https://")
    assert detect_survey_provider("https://wjx.cn.evil.example/vj/example.aspx", default="") == ""


@pytest.mark.asyncio
async def test_client_keeps_callers_client_open() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="")))
    SurveyClient(client)
    await client.get("https://example.test")
    assert not client.is_closed
    await client.aclose()
    assert client.is_closed


@pytest.mark.asyncio
async def test_parse_rejects_unknown_url_without_request() -> None:
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(UnsupportedSurveyError):
            await SurveyClient(http_client).parse("https://example.invalid/survey")
    assert not called


@pytest.mark.asyncio
async def test_parse_wjx_returns_public_definition() -> None:
    html = """
    <html><head><title>集成测试 - 问卷星</title></head><body>
      <div id="divQuestion"><fieldset>
        <div topic="1" id="div1" type="3">
          <div class="topichtml">1. 选择</div>
          <div class="ui-controlgroup"><div><span class="label">甲</span></div><div><span class="label">乙</span></div></div>
        </div>
      </fieldset></div>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "www.wjx.cn"
        return httpx.Response(200, text=html)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        definition = await SurveyClient(http_client).parse("https://www.wjx.cn/vj/integration.aspx")

    assert definition.provider == "wjx"
    assert definition.title == "集成测试"
    assert definition.questions[0].type_code == "3"
    assert definition.questions[0].provider_type == "3"
    assert definition.questions[0].option_texts == ("甲", "乙")


@pytest.mark.asyncio
async def test_parse_classifies_provider_errors(monkeypatch) -> None:
    async def unavailable(_url):
        raise RuntimeError("问卷已停止")

    async def broken(_url):
        raise RuntimeError("响应格式损坏")

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200))) as http_client:
        client = SurveyClient(http_client)
        monkeypatch.setattr(client_module, "parse_survey", unavailable)
        with pytest.raises(SurveyUnavailableError, match="已停止"):
            await client.parse("https://www.wjx.cn/vj/error.aspx")

        monkeypatch.setattr(client_module, "parse_survey", broken)
        with pytest.raises(SurveyParseError, match="响应格式损坏"):
            await client.parse("https://www.wjx.cn/vj/error.aspx")


def test_resolve_provider_rejects_unknown_and_mismatched_configuration() -> None:
    with pytest.raises(UnsupportedSurveyError, match="不支持"):
        SurveyClient._resolve_provider(RunConfig(url="https://example.invalid"))
    with pytest.raises(UnsupportedSurveyError, match="不一致"):
        SurveyClient._resolve_provider(
            RunConfig(url="https://www.wjx.cn/vj/demo.aspx", provider="qq")
        )
    assert (
        SurveyClient._resolve_provider(RunConfig(url="https://wj.qq.com/s/123", provider="qq"))
        == "qq"
    )


@pytest.mark.asyncio
async def test_submit_builds_one_attempt_and_preserves_failure_as_result(monkeypatch) -> None:
    captured = []

    async def successful_fill(execution, state, **kwargs):
        captured.append((execution, state, kwargs))
        return True

    config = RunConfig(
        url="https://www.wjx.cn/vj/demo.aspx",
        provider="wjx",
        target=8,
        concurrency=4,
        questions=[
            QuestionConfig(
                question_type="single",
                probabilities=[1, 0],
                question_num=1,
                option_count=2,
            )
        ],
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200))) as http_client:
        client = SurveyClient(http_client)
        monkeypatch.setattr(client_module, "fill_survey_http", successful_fill)
        success = await client.submit(config)

        async def failing_fill(*_args, **_kwargs):
            raise RuntimeError("提交端拒绝")

        monkeypatch.setattr(client_module, "fill_survey_http", failing_fill)
        failure = await client.submit(SubmissionRequest(config=config))

    execution, state, kwargs = captured[0]
    assert success.success is True and success.error is None
    assert execution.target_num == 8
    assert execution.num_threads == 4
    assert execution.question_config_index_map == {1: ("single", 0)}
    assert state.config is execution
    assert kwargs["provider"] == "wjx"
    assert kwargs["thread_name"] == "surveycore"
    assert failure.success is False and failure.error == "提交端拒绝"


@pytest.mark.asyncio
async def test_submit_reports_unconfirmed_provider_result(monkeypatch) -> None:
    async def unconfirmed(*_args, **_kwargs):
        return False

    config = RunConfig(url="https://wj.qq.com/s/123", provider="qq")
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200))) as http_client:
        monkeypatch.setattr(client_module, "fill_survey_http", unconfirmed)
        result = await SurveyClient(http_client).submit(config)

    assert result.provider == "qq"
    assert result.success is False
    assert result.error == "平台未确认提交成功"


@pytest.mark.asyncio
async def test_run_parses_once_submits_each_attempt_and_applies_interval(monkeypatch) -> None:
    survey = SurveyDefinition(
        provider="wjx",
        title="测试问卷",
        url="https://www.wjx.cn/vj/demo.aspx",
        questions=(SurveyQuestion(num=1, title="单选", type_code="3", options=2),),
    )
    submitted = []
    sleeps = []
    config = RunConfig(
        url=survey.url,
        provider="wjx",
        target=3,
        concurrency=1,
        submit_interval=(2, 4),
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200))) as http_client:
        client = SurveyClient(http_client)

        async def fake_parse(url):
            assert url == survey.url
            return survey

        async def fake_submit(request):
            submitted.append(request)
            return SubmissionResult(0, "wjx", True, 0.01)

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr(client, "parse", fake_parse)
        monkeypatch.setattr(client, "submit", fake_submit)
        monkeypatch.setattr(client_module.random, "uniform", lambda low, high: (low + high) / 2)
        monkeypatch.setattr(client_module.asyncio, "sleep", fake_sleep)

        results = [result async for result in client.run(config)]

    assert [result.attempt for result in results] == [1, 2, 3]
    assert sleeps == [3.0, 3.0]
    assert len(submitted) == 3
    assert all(request.config.target == 1 for request in submitted)
    assert all(request.survey is survey for request in submitted)
