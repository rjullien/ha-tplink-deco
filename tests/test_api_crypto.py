"""Tests for API encrypt/decrypt and session setup."""

from __future__ import annotations

import pytest

from custom_components.tplink_deco.api import TplinkDecoApi
from custom_components.tplink_deco.exceptions import EmptyDataException


def _prime_api_crypto(api: TplinkDecoApi) -> None:
    from Crypto.PublicKey import RSA as CryptoRSA

    sign_key = CryptoRSA.generate(1024)
    api._seq = 100
    api._aes_key = 1234567890123456
    api._aes_iv = 6543210987654321
    api._aes_key_bytes = str(api._aes_key).encode()
    api._aes_iv_bytes = str(api._aes_iv).encode()
    api._sign_rsa_n = int(sign_key.n)
    api._sign_rsa_e = int(sign_key.e)


def test_api_init_computes_auth_hash(api):
    import hashlib

    expected = hashlib.md5(b"adminpassword").hexdigest()
    assert api._auth_hash == expected


def test_encode_payload_roundtrip(api):
    _prime_api_crypto(api)
    payload = api._encode_payload({"operation": "read"})
    assert payload.startswith("sign=")
    assert "&data=" in payload


def test_decrypt_data_valid_payload(api):
    _prime_api_crypto(api)
    inner = {"error_code": 0, "result": {"device_list": []}}
    encoded = api._encode_data(inner)
    result = api._decrypt_data("List Devices", encoded)
    assert result == inner


def test_decrypt_data_invalid_payload_raises(api):
    _prime_api_crypto(api)
    with pytest.raises(Exception):
        api._decrypt_data("List Devices", "YWJj")  # valid base64, invalid ciphertext


@pytest.mark.asyncio
async def test_async_logout_without_session_is_noop(api, mock_session):
    await api.async_logout()
    mock_session.post.assert_not_called()
    assert api._stok is None
