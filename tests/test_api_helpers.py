"""Tests for pure API helper functions."""

from __future__ import annotations

import base64

import pytest

from custom_components.tplink_deco.api import aes_decrypt
from custom_components.tplink_deco.api import aes_encrypt
from custom_components.tplink_deco.api import byte_len
from custom_components.tplink_deco.api import check_data_error_code
from custom_components.tplink_deco.api import decode_name_with_fallback
from custom_components.tplink_deco.api import normalize_name
from custom_components.tplink_deco.api import rsa_encrypt
from custom_components.tplink_deco.exceptions import TimeoutException
from custom_components.tplink_deco.exceptions import UnexpectedApiException


def test_normalize_name_plain():
    assert normalize_name("Living Room") == "Living Room"


def test_normalize_name_legacy_error_decoding():
    assert normalize_name("<Error Decoding iPhone>") == "iPhone"


def test_normalize_name_empty_and_non_string():
    assert normalize_name("") == ""
    assert normalize_name(None) is None


def test_decode_name_with_fallback_base64():
    encoded = base64.b64encode("Deco Office".encode()).decode()
    assert decode_name_with_fallback(encoded) == "Deco Office"


def test_decode_name_with_fallback_invalid_base64():
    assert decode_name_with_fallback("not-base64!!!") == "not-base64!!!"


def test_decode_name_with_fallback_empty():
    assert decode_name_with_fallback("") == ""


def test_byte_len():
    assert byte_len(255) == 1
    assert byte_len(256) == 2


def test_aes_roundtrip_encrypt_decrypt():
    """aes_decrypt returns padded plaintext (padding stripped by _decrypt_data)."""
    key = b"1234567890123456"
    iv = b"1234567890123456"
    plaintext = b'{"operation":"read"}'
    ciphertext = aes_encrypt(key, iv, plaintext)
    decrypted = aes_decrypt(key, iv, ciphertext)
    assert decrypted.startswith(plaintext)
    assert len(decrypted) >= len(plaintext)


def test_check_data_error_code_timeout():
    with pytest.raises(TimeoutException):
        check_data_error_code("List Devices", {"error_code": "timeout"})


def test_check_data_error_code_unexpected():
    with pytest.raises(UnexpectedApiException):
        check_data_error_code("List Devices", {"error_code": -1})


def test_check_data_error_code_ok():
    check_data_error_code("List Devices", {"error_code": 0})


def test_rsa_encrypt_returns_hex_string():
    from Crypto.PublicKey import RSA as CryptoRSA

    key = CryptoRSA.generate(1024)
    result = rsa_encrypt(int(key.n), int(key.e), b"test")
    assert isinstance(result, str)
    assert all(c in "0123456789abcdef" for c in result)
