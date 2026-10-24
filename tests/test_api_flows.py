"""End-to-end API flow tests with realistic Deco fixtures."""

from __future__ import annotations

import json
import logging

import pytest

from custom_components.tplink_deco.api import TplinkDecoApi
from custom_components.tplink_deco.api import _redact_raw_response
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
async def test_async_login_full_flow(api, mock_session, caplog):
    caplog.set_level(logging.DEBUG, logger="custom_components.tplink_deco")
    mock_session.post.side_effect = _login_side_effect(api)
    stok = load_fixture("login_decrypted.json")["result"]["stok"]

    await api.async_login()

    assert api._stok == stok
    assert api._cookie == "sysauth=deadbeefcafebabe"
    assert api._seq == 42
    assert mock_session.post.await_count == 3
    assert stok not in caplog.text


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


@pytest.mark.parametrize(
    ("method_name", "fixture_name"),
    [
        ("async_list_devices", "device_list_decrypted.json"),
        ("async_list_clients", "client_list_decrypted.json"),
        ("async_get_performance", "performance_decrypted.json"),
    ],
)
@pytest.mark.asyncio
async def test_decrypted_api_responses_log_raw_payloads(
    api, mock_session, caplog, method_name, fixture_name
):
    caplog.set_level(logging.DEBUG, logger="custom_components.tplink_deco")
    prime_session_api(api)
    api._stok = "sessiontoken"
    api._cookie = "sysauth=abc"
    response_data = load_fixture(fixture_name)
    mock_session.post.return_value = make_response(
        wrap_encrypted_response(response_data, api)
    )

    method = getattr(api, method_name)
    if method_name == "async_list_clients":
        await method("AA:BB:CC:DD:EE:01")
    else:
        await method()

    raw_logs = [
        record.message
        for record in caplog.records
        if record.name == "custom_components.tplink_deco.api"
        and " raw response: " in record.message
    ]
    assert len(raw_logs) == 1
    assert mock_session.post.await_count == 1
    assert json.dumps(response_data, ensure_ascii=False) in raw_logs[0]
    if method_name == "async_list_clients":
        mac = response_data["result"]["client_list"][0]["mac"]
        assert mac in raw_logs[0]


@pytest.mark.asyncio
async def test_raw_response_logging_is_disabled_at_info(api, mock_session, caplog):
    caplog.set_level(logging.INFO, logger="custom_components.tplink_deco")
    prime_session_api(api)
    api._stok = "sessiontoken"
    api._cookie = "sysauth=abc"
    response_data = load_fixture("client_list_decrypted.json")
    mock_session.post.return_value = make_response(
        wrap_encrypted_response(response_data, api)
    )

    await api.async_list_clients("AA:BB:CC:DD:EE:01")

    assert "raw response" not in caplog.text
    assert mock_session.post.await_count == 1


@pytest.mark.asyncio
async def test_async_reboot_logs_redacted_raw_response(api, mock_session, caplog):
    caplog.set_level(logging.DEBUG, logger="custom_components.tplink_deco")
    prime_session_api(api)
    api._stok = "sessiontoken"
    api._cookie = "sysauth=abc"
    response_data = {
        "error_code": 0,
        "result": {
            "mac": "AA:BB:CC:DD:EE:01",
            "nested": {"Token": "sensitive-value"},
        },
    }
    mock_session.post.return_value = make_response(
        wrap_encrypted_response(response_data, api)
    )

    await api.async_reboot_decos(["AA:BB:CC:DD:EE:01"])

    raw_logs = [
        record.message
        for record in caplog.records
        if " raw response: " in record.message
    ]
    assert len(raw_logs) == 1
    assert mock_session.post.await_count == 1
    assert '"Token": "**REDACTED**"' in raw_logs[0]
    assert "sensitive-value" not in caplog.text
    assert "AA:BB:CC:DD:EE:01" in raw_logs[0]


def test_redact_raw_response_recursively_preserves_identifiers():
    data = {
        "mac": "AA:BB:CC:DD:EE:01",
        "nested": [
            {
                "StOk": "session-secret",
                "PASSWORD": "admin-secret",
                "child": {"Token": "api-secret", "Cookie": "cookie-secret"},
            }
        ],
    }

    redacted = _redact_raw_response(data)

    assert redacted == {
        "mac": "AA:BB:CC:DD:EE:01",
        "nested": [
            {
                "StOk": "**REDACTED**",
                "PASSWORD": "**REDACTED**",
                "child": {
                    "Token": "**REDACTED**",
                    "Cookie": "**REDACTED**",
                },
            }
        ],
    }
    assert data["nested"][0]["StOk"] == "session-secret"


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
