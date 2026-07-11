"""Tests for API encrypt/decrypt and session setup."""

from __future__ import annotations

import pytest

from custom_components.tplink_deco.api import byte_len
from custom_components.tplink_deco.exceptions import EmptyDataException

from tests.crypto_fixtures import load_fixture
from tests.crypto_fixtures import prime_session_api


def test_api_init_computes_auth_hash(api):
    import hashlib

    expected = hashlib.md5(b"adminpassword").hexdigest()
    assert api._auth_hash == expected


def test_encode_payload_embeds_golden_encrypted_data(api):
    vectors = load_fixture("crypto_vectors.json")
    prime_session_api(api)

    payload = api._encode_payload({"operation": "read"})

    assert payload.startswith("sign=")
    assert "&data=" in payload
    assert vectors["read_operation_data_b64"].replace("+", "%2B").replace("=", "%3D") in (
        payload
    )
    sign_hex = payload.split("&data=")[0].removeprefix("sign=")
    assert len(sign_hex) == byte_len(api._sign_rsa_n) * 2


def test_decrypt_data_golden_login_vector(api):
    vectors = load_fixture("crypto_vectors.json")
    prime_session_api(api)

    result = api._decrypt_data("Login", vectors["login_data_b64"])

    assert result == load_fixture("login_decrypted.json")


def test_decrypt_data_device_list_fixture_roundtrip(api):
    prime_session_api(api)
    inner = load_fixture("device_list_decrypted.json")
    encoded = api._encode_data(inner)
    assert api._decrypt_data("List Devices", encoded) == inner


def test_decrypt_data_invalid_payload_raises(api):
    prime_session_api(api)
    with pytest.raises(Exception):
        api._decrypt_data("List Devices", "YWJj")


def test_clear_auth_clears_session_and_rsa_keys(api):
    """Stale RSA keys must be cleared so a Deco reboot cannot brick re-login."""
    prime_session_api(api)
    api._stok = "token"
    api._cookie = "sysauth=abc"

    api.clear_auth()

    assert api._seq is None
    assert api._stok is None
    assert api._cookie is None
    assert api._sign_rsa_n is None
    assert api._password_rsa_n is None


@pytest.mark.asyncio
async def test_async_logout_without_session_is_noop(api, mock_session):
    await api.async_logout()
    mock_session.post.assert_not_called()
    assert api._stok is None
