from __future__ import annotations

import asyncio
import traceback
from types import SimpleNamespace

import httpx
import pytest

from surveycore import RunConfig, SubmissionRequest, SurveyClient

SURVEYS = {
    "wjx": "https://v.wjx.cn/vm/ei3sVrE.aspx",
    "qq": "https://wj.qq.com/s2/26070328/fa89/",
    "credamo": "https://www.credamo.com/s/A73QR3ano",
}


async def run_case(provider: str, url: str) -> None:
    async with asyncio.timeout(240), httpx.AsyncClient(
        timeout=60,
        follow_redirects=True,
    ) as http:
        client = SurveyClient(http)
        survey = await client.parse(url)
        if survey.provider != provider or not survey.questions:
            raise RuntimeError(f"{provider}: 解析结果平台不匹配或没有题目")

        config = RunConfig(
            url=url,
            provider=provider,
            target=1,
            concurrency=1,
            answer_duration=(0, 0),
            submit_interval=(0, 0),
        )
        result = await client.submit(SubmissionRequest(config=config, survey=survey))
        if not result.success:
            raise RuntimeError(f"{provider}: {result.error}")
        print(f"[PASS] {provider}: submitted 1 response", flush=True)


async def run_regression() -> int:
    results = await asyncio.gather(
        *(run_case(provider, url) for provider, url in SURVEYS.items()),
        return_exceptions=True,
    )
    failed = False
    for provider, result in zip(SURVEYS, results, strict=True):
        if isinstance(result, BaseException):
            failed = True
            print(f"[FAIL] {provider}", flush=True)
            traceback.print_exception(result)
    return int(failed)


@pytest.mark.parametrize(
    ("parse_failure", "submit_failure"),
    [(None, None), (None, "wjx"), (None, "qq"), (None, "credamo"), ("wjx", None)],
)
@pytest.mark.asyncio
async def test_live_survey_regression(
    monkeypatch: pytest.MonkeyPatch, parse_failure: str | None, submit_failure: str | None
) -> None:
    providers = {url: provider for provider, url in SURVEYS.items()}
    parsed: list[str] = []
    submitted: list[SubmissionRequest] = []

    class Client:
        def __init__(self, http: httpx.AsyncClient) -> None:
            self.http = http

        async def parse(self, url: str) -> SimpleNamespace:
            provider = providers[url]
            parsed.append(provider)
            if provider == parse_failure:
                raise RuntimeError("unparseable survey")
            return SimpleNamespace(provider=provider, questions=(object(),))

        async def submit(self, request: SubmissionRequest) -> SimpleNamespace:
            submitted.append(request)
            return SimpleNamespace(
                success=request.config.provider != submit_failure,
                error="submission rejected",
            )

    monkeypatch.setitem(globals(), "SurveyClient", Client)

    assert await run_regression() == int(parse_failure is not None or submit_failure is not None)
    assert sorted(parsed) == ["credamo", "qq", "wjx"]
    expected = {"credamo", "qq", "wjx"} - {parse_failure}
    assert len(submitted) == len(expected)
    assert {request.config.provider for request in submitted} == expected
    for request in submitted:
        assert request.config.target == request.config.concurrency == 1
        assert request.survey is not None
        assert request.survey.provider == request.config.provider


def main() -> int:
    return asyncio.run(run_regression())


if __name__ == "__main__":
    raise SystemExit(main())
