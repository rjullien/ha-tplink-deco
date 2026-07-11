"""Tests for custom exception types."""

from custom_components.tplink_deco.exceptions import LoginInvalidException


def test_login_invalid_exception_message():
    err = LoginInvalidException(3)
    assert err.attempts_remaining == 3
    assert "3 attempts remaining" in str(err)
