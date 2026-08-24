from __future__ import annotations

import httpx

from .errors import ConfigError


def require_async_client(client: object) -> httpx.AsyncClient:
    if not isinstance(client, httpx.AsyncClient):
        raise ConfigError("SurveyClient 必须接收调用方创建的 httpx.AsyncClient")
    return client

