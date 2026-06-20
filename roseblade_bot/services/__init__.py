"""
EVA Assistant service infrastructure package.
Copyright (c) 2026 Steve Dogs Studio.
"""

from roseblade_bot.services.http import HttpRequestError, fetch_bytes, fetch_json, http_session

__all__ = (
    "HttpRequestError",
    "fetch_bytes",
    "fetch_json",
    "http_session",
)
