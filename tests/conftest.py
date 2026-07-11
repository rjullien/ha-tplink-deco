"""Pytest configuration and shared fixtures."""

from __future__ import annotations

from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import aiohttp
import pytest

from custom_components.tplink_deco.api import TplinkDecoApi


@pytest.fixture
def mock_session() -> MagicMock:
    """Aiohttp client session with async post mock."""
    session = MagicMock(spec=aiohttp.ClientSession)
    session.post = AsyncMock()
    return session


@pytest.fixture
def api(mock_session: MagicMock) -> TplinkDecoApi:
    """API client pointed at a local http Deco host."""
    return TplinkDecoApi(
        session=mock_session,
        host="http://192.168.1.1",
        username="admin",
        password="password",
        verify_ssl=False,
    )
