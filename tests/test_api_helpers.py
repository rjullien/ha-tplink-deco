"""Tests for pure API helper functions."""

from __future__ import annotations

import base64
import json

import pytest
from Crypto.PublicKey import RSA as CryptoRSA

from custom_components.tplink_deco.api import aes_decrypt
from custom_components.tplink_deco.api import aes_encrypt
from custom_components.tplink_deco.api import byte_len
from custom_components.tplink_deco.api import check_data_error_code
from custom_components.tplink_deco.api import decode_name_with_fallback
from custom_components.tplink_deco.api import normalize_name
from custom_components.tplink_deco.api import rsa_encrypt
from custom_components.tplink_deco.exceptions import TimeoutException
from custom_components.tplink_deco.exceptions import UnexpectedApiException

from tests.crypto_fixtures import load_fixture


def test_decode_name_with_fallback_base64_and_legacy():
    encoded = base64.b64encode("Deco Office".encode()).decode()
    assert decode_name_with_fallback(encoded) == "Deco Office"
    assert decode_name_with_fallback("<Error Decoding iPhone>") == "iPhone"
    assert decode_name_with_fallback("not-base64!!!") == "not-base64!!!"


def test_aes_golden_vector_matches_read_operation():
    vectors = load_fixture("crypto_vectors.json")
    key = str(vectors["aes_key"]).encode()
    iv = str(vectors["aes_iv"]).encode()
    plaintext = json.dumps({"operation": "read"}, separators=(",", ":")).encode()
    assert base64.b64encode(aes_encrypt(key, iv, plaintext)).decode() == (
        vectors["read_operation_data_b64"]
    )


def test_rsa_sign_uses_seq_plus_payload_length():
    vectors = load_fixture("crypto_vectors.json")
    auth = load_fixture("auth_response.json")
    auth_key = auth["result"]["key"]
    n = int(auth_key[0], 16)
    e = int(auth_key[1], 16)

    import hashlib

    data_b64 = vectors["read_operation_data_b64"]
    sign_text = (
        f"k={vectors['aes_key']}&i={vectors['aes_iv']}"
        f"&h={hashlib.md5(b'adminpassword').hexdigest()}"
        f"&s={vectors['seq'] + len(data_b64)}"
    )
    sign = rsa_encrypt(n, e, sign_text.encode())

    assert len(sign) == byte_len(n) * 2
    assert all(c in "0123456789abcdef" for c in sign)


def test_rsa_encrypt_splits_large_plaintext_into_blocks():
    key = CryptoRSA.generate(1024)
    n, e = int(key.n), int(key.e)
    block_bytes = byte_len(n) - 11
    plaintext = b"a" * (block_bytes * 2 + 5)

    encrypted = rsa_encrypt(n, e, plaintext)

    blocks = (len(plaintext) + block_bytes - 1) // block_bytes
    assert len(encrypted) == blocks * byte_len(n) * 2


def test_byte_len_avoids_float_precision_on_large_moduli():
    # Regression: math.log2 can round up near powers of two.
    near_power_of_two = (1 << 1024) + 1
    assert byte_len(near_power_of_two) == 129


def test_check_data_error_code_timeout_and_unexpected():
    with pytest.raises(TimeoutException):
        check_data_error_code("List Devices", {"error_code": "timeout"})
    with pytest.raises(UnexpectedApiException):
        check_data_error_code("List Devices", {"error_code": -1})
    check_data_error_code("List Devices", {"error_code": 0})


def test_normalize_name_passthrough_and_legacy():
    assert normalize_name("Living Room") == "Living Room"
    assert normalize_name("<Error Decoding iPhone>") == "iPhone"
    assert normalize_name("") == ""
    assert normalize_name(None) is None
