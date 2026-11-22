from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

REGRESSION_PATH = Path(__file__).with_name("live_survey_regression.py")
REGRESSION_SPEC = importlib.util.spec_from_file_location("live_survey_regression", REGRESSION_PATH)
assert REGRESSION_SPEC is not None and REGRESSION_SPEC.loader is not None
regression = importlib.util.module_from_spec(REGRESSION_SPEC)
REGRESSION_SPEC.loader.exec_module(regression)


@pytest.mark.parametrize("failed_provider", [None, "wjx"])
@pytest.mark.asyncio
async def test_live_regression_submits_once_per_survey_and_fails_closed(
    monkeypatch, failed_provider
) -> None:
    parsed = []
    submitted = []

    class Client:
        def __init__(self, http):
            self.http = http

        async def parse(self, url):
            provider = next(name for name, value in regression.SURVEYS.items() if value == url)
            parsed.append(provider)
            return SimpleNamespace(provider=provider, questions=(object(),))

        async def submit(self, request):
            submitted.append(request)
            return SimpleNamespace(
                success=request.config.provider != failed_provider,
                error="submission rejected",
            )

    monkeypatch.setattr(regression, "SurveyClient", Client)

    assert await regression.run_regression() == int(failed_provider is not None)
    assert sorted(parsed) == sorted(regression.SURVEYS)
    assert len(submitted) == len(regression.SURVEYS)
    assert {request.config.provider for request in submitted} == set(regression.SURVEYS)
    assert all(request.config.target == request.config.concurrency == 1 for request in submitted)
    assert all(request.survey.provider == request.config.provider for request in submitted)


@pytest.mark.parametrize("failed_provider", ["wjx"])
@pytest.mark.asyncio
async def test_parse_failure_prevents_submission_and_fails_regression(
    monkeypatch, failed_provider
) -> None:
    submitted = []

    class Client:
        def __init__(self, http):
            self.http = http

        async def parse(self, url):
            provider = next(name for name, value in regression.SURVEYS.items() if value == url)
            if provider == failed_provider:
                raise RuntimeError("unparseable survey")
            return SimpleNamespace(provider=provider, questions=(object(),))

        async def submit(self, request):
            submitted.append(request)
            return SimpleNamespace(success=True, error=None)

    monkeypatch.setattr(regression, "SurveyClient", Client)

    assert await regression.run_regression() == 1
    assert all(request.config.provider != failed_provider for request in submitted)
