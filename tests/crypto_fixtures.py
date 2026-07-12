"""Fixture loading and crypto helpers for API flow tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from custom_components.tplink_deco.api import TplinkDecoApi

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / name).read_text())


def prime_session_api(api: TplinkDecoApi) -> dict[str, Any]:
    """Prime API client with fixed session keys from test fixtures."""
    vectors = load_fixture("crypto_vectors.json")
    auth = load_fixture("auth_response.json")
    keys = load_fixture("keys_response.json")

    api._aes_key = vectors["aes_key"]
    api._aes_iv = vectors["aes_iv"]
    api._aes_key_bytes = str(api._aes_key).encode()
    api._aes_iv_bytes = str(api._aes_iv).encode()

    password = keys["result"]["password"]
    api._password_rsa_n = int(password[0], 16)
    api._password_rsa_e = int(password[1], 16)

    auth_key = auth["result"]["key"]
    api._sign_rsa_n = int(auth_key[0], 16)
    api._sign_rsa_e = int(auth_key[1], 16)
    api._seq = auth["result"]["seq"]

    return vectors


def wrap_encrypted_response(
    inner: dict[str, Any], api: TplinkDecoApi
) -> dict[str, Any]:
    """Build a realistic Deco JSON envelope with encrypted data field."""
    return {"error_code": 0, "data": api._encode_data(inner)}


def expected_device_list_after_decode() -> list[dict[str, Any]]:
    """Device list as returned by async_list_devices after name decoding."""
    devices = load_fixture("device_list_decrypted.json")["result"]["device_list"]
    expected = [dict(device) for device in devices]
    expected[0]["custom_nickname"] = "Living Room"
    return expected


def expected_client_list_after_decode() -> list[dict[str, Any]]:
    """Client list as returned by async_list_clients after name decoding."""
    clients = load_fixture("client_list_decrypted.json")["result"]["client_list"]
    expected = [dict(client) for client in clients]
    expected[0]["name"] = "Phone"
    expected[1]["name"] = "Laptop"
    return expected
