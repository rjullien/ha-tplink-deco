"""Tests for config flow helpers."""

from __future__ import annotations

from homeassistant.components.device_tracker.const import CONF_SCAN_INTERVAL

from custom_components.tplink_deco.config_flow import SCAN_INTERVAL_OPTIONS
from custom_components.tplink_deco.config_flow import _ensure_user_input_optionals
from custom_components.tplink_deco.config_flow import _get_scan_interval
from custom_components.tplink_deco.config_flow import _normalize_scan_interval
from custom_components.tplink_deco.const import CONF_CLIENT_POSTFIX
from custom_components.tplink_deco.const import CONF_CLIENT_PREFIX
from custom_components.tplink_deco.const import CONF_DECO_POSTFIX
from custom_components.tplink_deco.const import CONF_DECO_PREFIX
from custom_components.tplink_deco.const import DEFAULT_SCAN_INTERVAL


def test_get_scan_interval_default():
    assert _get_scan_interval({}) == str(DEFAULT_SCAN_INTERVAL)


def test_get_scan_interval_extended_fork_option():
    assert _get_scan_interval({CONF_SCAN_INTERVAL: 180}) == "180"


def test_get_scan_interval_string_value():
    assert _get_scan_interval({CONF_SCAN_INTERVAL: "120"}) == "120"


def test_get_scan_interval_invalid_falls_back_to_default():
    assert _get_scan_interval({CONF_SCAN_INTERVAL: 999}) == str(DEFAULT_SCAN_INTERVAL)
    assert _get_scan_interval({CONF_SCAN_INTERVAL: "invalid"}) == str(
        DEFAULT_SCAN_INTERVAL
    )


def test_normalize_scan_interval_converts_string():
    data = {CONF_SCAN_INTERVAL: "240"}
    _normalize_scan_interval(data)
    assert data[CONF_SCAN_INTERVAL] == 240


def test_get_scan_interval_covers_all_fork_options():
    for value in SCAN_INTERVAL_OPTIONS:
        assert _get_scan_interval({CONF_SCAN_INTERVAL: value}) == str(value)


def test_ensure_user_input_optionals_fills_missing_keys():
    data: dict = {}
    _ensure_user_input_optionals(data)
    assert data[CONF_CLIENT_PREFIX] == ""
    assert data[CONF_CLIENT_POSTFIX] == ""
    assert data[CONF_DECO_PREFIX] == ""
    assert data[CONF_DECO_POSTFIX] == ""
