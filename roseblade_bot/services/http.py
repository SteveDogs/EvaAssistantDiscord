"""
EVA Assistant shared HTTP helpers.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
import json
from typing import Any

import aiohttp


class HttpRequestError(RuntimeError):
    def __init__(self, status: int, headers: Mapping[str, str], body: bytes) -> None:
        super().__init__(f"HTTP request failed with status {status}")
        self.status = status
        self.headers = headers
        self.body = body


@asynccontextmanager
async def http_session(
    *,
    timeout_total: float,
    headers: Mapping[str, str] | None = None,
) -> AsyncIterator[aiohttp.ClientSession]:
    timeout = aiohttp.ClientTimeout(total=timeout_total)
    async with aiohttp.ClientSession(timeout=timeout, headers=dict(headers or {})) as session:
        yield session


async def fetch_bytes(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, str | int] | None = None,
    timeout_total: float,
) -> tuple[bytes, Mapping[str, str]]:
    async with http_session(timeout_total=timeout_total, headers=headers) as session:
        async with session.get(url, params=params) as response:
            body = await response.read()
            if response.status >= 400:
                raise HttpRequestError(response.status, response.headers, body)
            return body, response.headers


async def fetch_json(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, str | int] | None = None,
    timeout_total: float,
) -> tuple[Any, Mapping[str, str]]:
    body, response_headers = await fetch_bytes(
        url,
        headers=headers,
        params=params,
        timeout_total=timeout_total,
    )
    return json.loads(body.decode("utf-8")), response_headers
