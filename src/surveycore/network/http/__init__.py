from __future__ import annotations

from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any, AsyncIterator

import httpx

_current_client: ContextVar[httpx.AsyncClient | None] = ContextVar("surveycore_http_client", default=None)


@asynccontextmanager
async def bind(client: httpx.AsyncClient) -> AsyncIterator[None]:
    token = _current_client.set(client)
    try:
        yield
    finally:
        _current_client.reset(token)


def _client() -> httpx.AsyncClient:
    client = _current_client.get()
    if client is None:
        raise RuntimeError("surveycore 请求必须在 SurveyClient 提供的 AsyncClient 上下文中执行")
    return client


def current_client() -> httpx.AsyncClient:
    return _client()


async def request(method: str, url: str, **kwargs: Any) -> httpx.Response:
    # 代理由调用方绑定的 AsyncClient/transport 管理；旧 provider 的参数被丢弃。
    kwargs.pop("proxies", None)
    kwargs.pop("proxy", None)
    return await _client().request(method, url, **kwargs)


async def get(url: str, **kwargs: Any) -> httpx.Response:
    return await request("GET", url, **kwargs)


async def post(url: str, **kwargs: Any) -> httpx.Response:
    return await request("POST", url, **kwargs)


async def put(url: str, **kwargs: Any) -> httpx.Response:
    return await request("PUT", url, **kwargs)


async def delete(url: str, **kwargs: Any) -> httpx.Response:
    return await request("DELETE", url, **kwargs)


async def aget(url: str, **kwargs: Any) -> httpx.Response:
    return await get(url, **kwargs)


async def apost(url: str, **kwargs: Any) -> httpx.Response:
    return await post(url, **kwargs)


__all__ = ["aget", "apost", "bind", "current_client", "delete", "get", "post", "put", "request"]
