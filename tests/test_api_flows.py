"""End-to-end API flow tests with realistic Deco fixtures."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from custom_components.tplink_deco.api import TplinkDecoApi
from custom_components.tplink_deco.exceptions import LoginInvalidException

from tests.crypto_fixtures import expected_client_list_after_decode
from tests.crypto_fixtures import expected_device_list_after_decode
from tests.crypto_fixtures import load_fixture
from tests.crypto_fixtures import prime_session_api
from tests.crypto_fixtures import wrap_encrypted_response
from tests.helpers import make_response


def _login_side_effect(api: TplinkDecoApi):
    """Return mocked responses for keys, auth, and login calls."""
    keys = load_fixture("keys_response.json")
    auth = load_fixture("auth_response.json")
    login_inner = load_fixture("login_decrypted.json")
    cookie = "sysauth=deadbeefcafebabe"

    async def _post(url, **kwargs):
        params = kwargs.get("params") or {}
        form = params.get("form")
        if form == "keys":
            return make_response(keys)
        if form == "auth":
            return make_response(auth)
        if form == "login":
            return make_response(
                wrap_encrypted_response(login_inner, api),
                set_cookie_headers=[f"{cookie}; path=/"],
            )
        raise AssertionError(f"Unexpected post form={form} url={url}")

    return _post


@pytest.mark.asyncio
async def test_async_login_full_flow(api, mock_session):
    mock_session.post.side_effect = _login_side_effect(api)

    await api.async_login()

    assert api._stok == "deadbeefcafebabe01234567"
    assert api._cookie == "sysauth=deadbeefcafebabe"
    assert api._seq == 42
    assert mock_session.post.await_count == 3


@pytest.mark.asyncio
async def test_async_login_invalid_password_clears_auth(api, mock_session):
    login_inner = {
        "error_code": -5002,
        "result": {"attemptsAllowed": 3},
    }

    async def _post(url, **kwargs):
        params = kwargs.get("params") or {}
        form = params.get("form")
        if form == "keys":
            return make_response(load_fixture("keys_response.json"))
        if form == "auth":
            return make_response(load_fixture("auth_response.json"))
        if form == "login":
            return make_response(wrap_encrypted_response(login_inner, api))
        raise AssertionError(f"Unexpected post form={form}")

    mock_session.post.side_effect = _post

    with pytest.raises(LoginInvalidException) as exc:
        await api.async_login()

    assert exc.value.attempts_remaining == 3
    assert api._stok is None
    assert api._seq is None


@pytest.mark.asyncio
async def test_async_list_devices_parses_fixture(api, mock_session):
    prime_session_api(api)
    api._stok = "sessiontoken"
    api._cookie = "sysauth=abc"

    device_inner = load_fixture("device_list_decrypted.json")

    mock_session.post.return_value = make_response(
        wrap_encrypted_response(device_inner, api)
    )

    devices = await api.async_list_devices()

    assert devices == expected_device_list_after_decode()
    call = mock_session.post.await_args
    assert call.kwargs["params"]["form"] == "device_list"
    assert "sign=" in call.kwargs["data"]
    assert "&data=" in call.kwargs["data"]


@pytest.mark.asyncio
async def test_async_list_clients_decodes_names(api, mock_session):
    prime_session_api(api)
    api._stok = "sessiontoken"
    api._cookie = "sysauth=abc"

    client_inner = load_fixture("client_list_decrypted.json")
    mock_session.post.return_value = make_response(
        wrap_encrypted_response(client_inner, api)
    )

    clients = await api.async_list_clients("AA:BB:CC:DD:EE:01")

    assert clients == expected_client_list_after_decode()
    call = mock_session.post.await_args
    assert call.kwargs["params"]["form"] == "client_list"


@pytest.mark.asyncio
async def test_async_get_performance_returns_fixture(api, mock_session):
    prime_session_api(api)
    api._stok = "sessiontoken"
    api._cookie = "sysauth=abc"

    perf_inner = load_fixture("performance_decrypted.json")
    mock_session.post.return_value = make_response(
        wrap_encrypted_response(perf_inner, api)
    )

    result = await api.async_get_performance()

    assert result == perf_inner
    call = mock_session.post.await_args
    assert call.kwargs["params"]["form"] == "performance"


@pytest.mark.asyncio
async def test_async_logout_sends_signed_payload_and_clears_auth(api, mock_session):
    prime_session_api(api)
    api._stok = "sessiontoken"
    api._cookie = "sysauth=abc"
    mock_session.post.return_value = make_response({"error_code": 0, "data": ""})

    await api.async_logout()

    call = mock_session.post.await_args
    assert call.kwargs["params"]["form"] == "logout"
    assert "sign=" in call.kwargs["data"]
    assert api._stok is None
    assert api._cookie is None


@pytest.mark.asyncio
async def test_empty_data_retry_relogins_once(api, mock_session):
    """Empty encrypted data triggers one re-login then succeeds."""
    prime_session_api(api)
    api._stok = "oldtoken"
    api._cookie = "sysauth=old"

    device_inner = load_fixture("device_list_decrypted.json")
    calls: list[str] = []

    async def _post(url, **kwargs):
        params = kwargs.get("params") or {}
        form = params.get("form", "device_list")
        calls.append(form)
        if form in ("keys", "auth", "login"):
            return await _login_side_effect(api)(url, **kwargs)
        if len([c for c in calls if c == "device_list"]) == 1:
            return make_response({"error_code": 0, "data": ""})
        return make_response(wrap_encrypted_response(device_inner, api))

    mock_session.post.side_effect = _post

    devices = await api.async_list_devices()

    assert devices == expected_device_list_after_decode()
    assert "login" in calls
    assert calls.count("device_list") == 2
