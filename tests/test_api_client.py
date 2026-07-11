"""Tests for TplinkDecoApi network and session behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import aiohttp
import pytest
from aiohttp.hdrs import SET_COOKIE

from custom_components.tplink_deco.api import TplinkDecoApi
from custom_components.tplink_deco.exceptions import EmptyDataException
from custom_components.tplink_deco.exceptions import ForbiddenException
from custom_components.tplink_deco.exceptions import TimeoutException

from tests.helpers import make_redirect_history
from tests.helpers import make_response


@pytest.mark.asyncio
async def test_async_post_upgrades_host_on_http_to_https_redirect(api, mock_session):
    """Regression for upstream #539 / HA 2026.7 aiohttp cookie drop."""
    history = make_redirect_history()
    response = make_response(
        {"error_code": 0, "data": "abc"},
        url="https://192.168.1.1/cgi-bin/luci/;stok=abc/admin/device",
        history=history,
    )
    mock_session.post.return_value = response

    result = await api._async_post(
        "List Devices",
        "http://192.168.1.1/cgi-bin/luci/;stok=abc/admin/device",
        params={"form": "device_list"},
        data="payload",
    )

    assert result == {"error_code": 0, "data": "abc"}
    assert api._host == "https://192.168.1.1"


@pytest.mark.asyncio
async def test_async_post_no_upgrade_when_already_https(api, mock_session):
    api._host = "https://192.168.1.1"
    response = make_response({"error_code": 0})
    mock_session.post.return_value = response

    await api._async_post("List Devices", f"{api._host}/path", params={}, data="x")

    assert api._host == "https://192.168.1.1"


@pytest.mark.asyncio
async def test_async_post_no_upgrade_on_different_host_redirect(api, mock_session):
    """Only same-host scheme changes should rewrite the base URL."""
    history = make_redirect_history(from_url="http://192.168.0.1/path")
    response = make_response(
        {"error_code": 0},
        url="https://192.168.1.1/path",
        history=history,
    )
    mock_session.post.return_value = response

    await api._async_post("Fetch keys", f"{api._host}/path", params={}, data="x")

    assert api._host == "http://192.168.1.1"


@pytest.mark.asyncio
async def test_async_post_parses_set_cookie(api, mock_session):
    response = make_response(
        {"error_code": 0},
        set_cookie_headers=["sysauth=deadbeef; path=/"],
    )
    mock_session.post.return_value = response

    await api._async_post("Login", f"{api._host}/path", params={}, data="x")

    assert api._cookie == "sysauth=deadbeef"


@pytest.mark.asyncio
async def test_async_post_non_dict_json_raises_empty_data(api, mock_session):
    response = make_response([])  # type: ignore[arg-type]
    mock_session.post.return_value = response

    with pytest.raises(EmptyDataException):
        await api._async_post("List Devices", f"{api._host}/path", params={}, data="x")


@pytest.mark.asyncio
async def test_async_post_timeout_raises(api, mock_session):
    mock_session.post.side_effect = TimeoutError()

    with pytest.raises(TimeoutException):
        await api._async_post("List Devices", f"{api._host}/path", params={}, data="x")


@pytest.mark.asyncio
async def test_async_post_403_clears_auth(api, mock_session):
    api._stok = "token"
    api._cookie = "sysauth=abc"
    api._seq = 1
    mock_session.post.side_effect = aiohttp.ClientResponseError(
        request_info=MagicMock(),
        history=(),
        status=403,
        message="Forbidden",
    )

    with pytest.raises(ForbiddenException):
        await api._async_post("List Devices", f"{api._host}/path", params={}, data="x")

    assert api._stok is None
    assert api._cookie is None


@pytest.mark.asyncio
async def test_async_post_502_clears_auth(api, mock_session):
    api._stok = "token"
    api._seq = 1
    mock_session.post.side_effect = aiohttp.ClientResponseError(
        request_info=MagicMock(),
        history=(),
        status=502,
        message="Bad Gateway",
    )

    with pytest.raises(aiohttp.ClientResponseError):
        await api._async_post("List Devices", f"{api._host}/path", params={}, data="x")

    assert api._stok is None


@pytest.mark.asyncio
async def test_async_post_connector_error_keeps_auth(api, mock_session):
    api._stok = "token"
    api._cookie = "sysauth=abc"
    api._seq = 1
    mock_session.post.side_effect = aiohttp.ClientConnectorError(
        connection_key=MagicMock(),
        os_error=OSError("connection refused"),
    )

    with pytest.raises(aiohttp.ClientConnectorError):
        await api._async_post("List Devices", f"{api._host}/path", params={}, data="x")

    assert api._stok == "token"
    assert api._cookie == "sysauth=abc"


def test_decrypt_data_empty_raises_without_clearing_auth(api):
    api._stok = "token"
    api._cookie = "sysauth=abc"

    with pytest.raises(EmptyDataException):
        api._decrypt_data("List Devices", "")

    assert api._stok == "token"
    assert api._cookie == "sysauth=abc"


def test_encode_sign_requires_login(api):
    with pytest.raises(EmptyDataException):
        api._encode_sign(10)
