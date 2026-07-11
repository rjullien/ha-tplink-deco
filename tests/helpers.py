"""Shared test helpers for mocked aiohttp responses."""

from __future__ import annotations

from unittest.mock import AsyncMock
from unittest.mock import MagicMock

from yarl import URL


def make_response(
    json_data: dict,
    *,
    url: str = "https://192.168.1.1/cgi-bin/luci/;stok=abc/admin/device",
    history: list | None = None,
    set_cookie_headers: list[str] | None = None,
) -> MagicMock:
    """Build a mocked aiohttp response."""
    response = MagicMock()
    response.history = history or []
    response.url = URL(url)
    response.raise_for_status = MagicMock()
    response.headers.getall = MagicMock(return_value=set_cookie_headers or [])
    response.json = AsyncMock(return_value=json_data)
    return response


def make_redirect_history(
    from_url: str = "http://192.168.1.1/cgi-bin/luci/;stok=abc/admin/device",
) -> list[MagicMock]:
    """History entry for http→https same-host redirect."""
    entry = MagicMock()
    entry.url = URL(from_url)
    return [entry]
