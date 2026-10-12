"""Tests for the legacy outer-session (local-web) API fallback."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

from Crypto.PublicKey import RSA
import aiohttp
import pytest

from custom_components.tplink_deco.api import TplinkDecoApi
from custom_components.tplink_deco.exceptions import EmptyDataException
from custom_components.tplink_deco.exceptions import TransientConnectionException
from tests.helpers import make_response


def _outer_rsa_key() -> RSA.RsaKey:
    return RSA.generate(1024)


def _setup_outer_session(api: TplinkDecoApi) -> None:
    key = _outer_rsa_key()
    api._outer_id = "outer-id"
    api._outer_rsa_n = key.n
    api._outer_rsa_e = key.e
    api._outer_seq = 0
    api._outer_aes_key = "1234567890123456"
    api._outer_aes_iv = "6543210987654321"
    api._outer_aes_key_bytes = api._outer_aes_key.encode()
    api._outer_aes_iv_bytes = api._outer_aes_iv.encode()


def test_security_encode_known_vector():
    # left XOR right over the challenge alphabet, 187 for out-of-range index
    result = TplinkDecoApi._security_encode("ab", "ab", "0123456789abcdef")
    assert result == "00"
    assert len(TplinkDecoApi._security_encode("a", "abcd", "0123456789abcdef")) == 4


def test_outer_payload_roundtrip(api):
    _setup_outer_session(api)
    payload = '{"operation":"read"}'
    encoded = api._encode_outer_payload(payload)
    assert encoded.startswith("sign=")
    assert "&data=" in encoded
    encrypted_b64 = encoded.split("&data=", 1)[1]
    assert api._decode_outer_payload(encrypted_b64) == payload


def test_encode_payload_outer_session_returns_plain_json(api):
    _setup_outer_session(api)
    result = api._encode_payload({"operation": "read"})
    assert json.loads(result) == {"operation": "read"}


def test_clear_auth_clears_outer_session(api):
    _setup_outer_session(api)
    api.clear_auth()
    assert api._outer_id is None
    assert api._outer_rsa_n is None
    assert api._outer_aes_key_bytes is None


@pytest.mark.asyncio
async def test_async_post_outer_session_decodes_and_rewrites_url(api, mock_session):
    _setup_outer_session(api)
    api._stok = "stok123"
    inner = {"error_code": 0, "result": {"ok": True}}
    response = make_response({})
    response.text = AsyncMock(
        return_value=api._encode_outer_payload(json.dumps(inner)).split("&data=", 1)[1]
    )
    mock_session.post.return_value = response

    result = await api._async_post(
        "List Clients",
        f"{api._host}/cgi-bin/luci/;stok={api._stok}/admin/client",
        params={"form": "client_list"},
        data="payload",
    )

    assert result == {"data": inner}
    kwargs = mock_session.post.call_args.kwargs
    assert kwargs["params"]["id"] == "outer-id"
    # The ;stok= prefix is stripped for the outer-session endpoint
    assert kwargs["params"]["form"] == "client_list"
    assert mock_session.post.call_args.args[0] == (f"{api._host}/admin/client")


@pytest.mark.asyncio
async def test_async_post_outer_session_empty_response_raises(api, mock_session):
    _setup_outer_session(api)
    response = make_response({})
    response.text = AsyncMock(return_value="")
    mock_session.post.return_value = response

    with pytest.raises(EmptyDataException):
        await api._async_post(
            "List Clients",
            f"{api._host}/cgi-bin/luci/;stok=stok/admin/client",
            params={},
            data="payload",
        )


def _outer_post_response(text: str, status: int = 200) -> MagicMock:
    response = MagicMock()
    response.status = status
    response.text = AsyncMock(return_value=text)
    response.raise_for_status = MagicMock()
    return response


@pytest.mark.asyncio
async def test_async_login_outer_session_handshake(api):
    key = _outer_rsa_key()
    api._async_outer_post = AsyncMock(
        side_effect=[
            _outer_post_response("l1\nl2\nl3\nCHALLENGE\nALPHABET", status=401),
            _outer_post_response("00000 enable ok"),
            _outer_post_response(f"00000\n{key.e:x}\n{key.n:x}\n7"),
            _outer_post_response("00000 login ok"),
            _outer_post_response("00000 set ok"),
        ]
    )

    await api._async_login_outer_session()

    assert api._outer_id is not None
    assert api._seq == 0
    assert api._stok == ""
    assert api._cookie == "outer=1"
    assert api._use_outer_session is False  # set by the caller, not the login


@pytest.mark.asyncio
async def test_async_login_falls_back_to_outer_session_on_401(api):
    api._async_fetch_keys = AsyncMock(
        side_effect=aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=401,
            message="Unauthorized",
        )
    )
    api._async_login_outer_session = AsyncMock()

    await api._async_login()

    api._async_login_outer_session.assert_awaited_once()
    assert api._use_outer_session is True


@pytest.mark.asyncio
async def test_async_login_no_outer_fallback_on_other_errors(api):
    api._async_fetch_keys = AsyncMock(
        side_effect=aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=500,
            message="Server Error",
        )
    )
    api._async_login_outer_session = AsyncMock()

    with pytest.raises(aiohttp.ClientResponseError):
        await api._async_login()

    api._async_login_outer_session.assert_not_awaited()
    assert api._use_outer_session is False


@pytest.mark.asyncio
async def test_async_post_payload_error_is_transient_and_keeps_auth(api, mock_session):
    api._stok = "token"
    api._cookie = "sysauth=abc"
    api._seq = 1
    mock_session.post.side_effect = aiohttp.ClientPayloadError("truncated")

    with pytest.raises(TransientConnectionException):
        await api._async_post("List Devices", f"{api._host}/path", params={}, data="x")

    assert api._stok == "token"
    assert api._cookie == "sysauth=abc"


@pytest.mark.asyncio
async def test_async_post_server_disconnect_is_transient_and_keeps_auth(
    api, mock_session
):
    api._stok = "token"
    api._cookie = "sysauth=abc"
    api._seq = 1
    mock_session.post.side_effect = aiohttp.ServerDisconnectedError()

    with pytest.raises(TransientConnectionException):
        await api._async_post("List Devices", f"{api._host}/path", params={}, data="x")

    assert api._stok == "token"
    assert api._cookie == "sysauth=abc"


@pytest.mark.asyncio
async def test_transient_connection_error_is_retried(api, mock_session):
    calls = 0

    async def flaky():
        nonlocal calls
        calls += 1
        if calls < 2:
            raise TransientConnectionException("boom")
        return {"result": "ok"}

    api._timeout_error_retries = 3
    with patch(
        "custom_components.tplink_deco.api.asyncio.sleep", new_callable=AsyncMock
    ) as sleep_mock:
        result = await api._async_call_with_retry(flaky)

    assert result == {"result": "ok"}
    assert calls == 2
    sleep_mock.assert_awaited_once_with(2)


@pytest.mark.asyncio
async def test_transient_connection_error_exhausts_retries(api, mock_session):
    async def always_fails():
        raise TransientConnectionException("boom")

    with patch(
        "custom_components.tplink_deco.api.asyncio.sleep", new_callable=AsyncMock
    ) as sleep_mock:
        with pytest.raises(TransientConnectionException):
            await api._async_call_with_retry(always_fails)

    assert sleep_mock.await_count == api._timeout_error_retries
