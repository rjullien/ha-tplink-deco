"""Tests for coordinator utility helpers."""

from __future__ import annotations

import pytest

from custom_components.tplink_deco.coordinator import filter_invalid_ip
from custom_components.tplink_deco.coordinator import kilobits_to_kilobytes
from custom_components.tplink_deco.coordinator import snake_case_to_title_space


def test_kilobits_to_kilobytes():
    assert kilobits_to_kilobytes(8000) == 1000.0
    assert kilobits_to_kilobytes(None) is None


def test_filter_invalid_ip():
    assert filter_invalid_ip("192.168.1.10") == "192.168.1.10"
    assert filter_invalid_ip("not-an-ip") is None


def test_snake_case_to_title_space():
    assert snake_case_to_title_space("guest_room_5g") == "Guest Room 5G"
