"""Tests for coordinator models and update logic."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import aiohttp
from homeassistant.exceptions import ConfigEntryAuthFailed
import pytest

from custom_components.tplink_deco.coordinator import (
    async_call_and_propagate_config_error,
)
from custom_components.tplink_deco.coordinator import TpLinkDeco
from custom_components.tplink_deco.coordinator import TpLinkDecoClient
from custom_components.tplink_deco.coordinator import TpLinkDecoData
from custom_components.tplink_deco.coordinator import TplinkDecoClientUpdateCoordinator
from custom_components.tplink_deco.coordinator import TplinkDecoUpdateCoordinator
from custom_components.tplink_deco.coordinator import filter_invalid_ip
from custom_components.tplink_deco.exceptions import LoginInvalidException


def _make_hass() -> MagicMock:
    hass = MagicMock()
    hass.loop.call_soon = MagicMock()
    return hass


def _make_config_entry() -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "test_entry"
    return entry


def _master_deco_dict(mac: str = "AA:BB:CC:DD:EE:01") -> dict:
    return {
        "mac": mac,
        "nickname": "master_deco",
        "device_ip": "192.168.1.1",
        "group_status": "connected",
        "inet_status": "online",
        "role": "master",
        "connection_type": "wifi",
        "signal_level": {"band2_4": -50, "band5": -60},
    }


def _slave_deco_dict(mac: str = "AA:BB:CC:DD:EE:02") -> dict:
    return {
        "mac": mac,
        "nickname": "bedroom",
        "device_ip": "192.168.1.2",
        "group_status": "connected",
        "inet_status": "connected",
        "role": "slave",
    }


class TestTpLinkDecoModel:
    def test_update_with_custom_nickname(self):
        deco = TpLinkDeco("AA:BB:CC:DD:EE:01")
        deco.update({"mac": "AA:BB:CC:DD:EE:01", "custom_nickname": "Office Deco"})
        assert deco.name == "Office Deco"

    def test_update_nickname_snake_case_and_invalid_ip(self):
        deco = TpLinkDeco("AA:BB:CC:DD:EE:01")
        deco.update(_slave_deco_dict())
        assert deco.name == "Bedroom"
        assert filter_invalid_ip("192.168.1.10") == "192.168.1.10"
        assert filter_invalid_ip("not-an-ip") is None
        assert deco.online is True
        assert deco.master is False
        assert deco.internet_online is True

    def test_update_master_and_performance_fields(self):
        deco = TpLinkDeco("AA:BB:CC:DD:EE:01")
        deco.update(_master_deco_dict())
        assert deco.master is True
        assert deco.ip_address == "192.168.1.1"
        assert deco.signal_band2_4 == -50

    def test_update_invalid_ip(self):
        deco = TpLinkDeco("AA:BB:CC:DD:EE:01")
        deco.update({"mac": "AA:BB:CC:DD:EE:01", "device_ip": "not-an-ip"})
        assert deco.ip_address is None

    def test_update_inet_status_bool(self):
        deco = TpLinkDeco("AA:BB:CC:DD:EE:01")
        deco.update({"mac": "AA:BB:CC:DD:EE:01", "inet_status": 1})
        assert deco.internet_online is True


class TestTpLinkDecoClientModel:
    def test_update_connected_client(self):
        client = TpLinkDecoClient("11:22:33:44:55:66")
        now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
        client.update(
            {
                "mac": "11:22:33:44:55:66",
                "name": "Phone",
                "ip": "192.168.1.50",
                "down_speed": 8000,
                "up_speed": 4000,
            },
            "AA:BB:CC:DD:EE:01",
            now,
        )
        assert client.name == "Phone"
        assert client.online is True
        assert client.down_kilobytes_per_s == 1000.0
        assert client.up_kilobytes_per_s == 500.0
        assert client.deco_mac == "AA:BB:CC:DD:EE:01"
        assert client.last_activity == now


@pytest.mark.asyncio
async def test_async_call_and_propagate_config_error_success():
    async def ok():
        return "done"

    assert await async_call_and_propagate_config_error(ok) == "done"


@pytest.mark.asyncio
async def test_async_call_and_propagate_config_error_auth():
    async def fail():
        raise LoginInvalidException(2)

    with pytest.raises(ConfigEntryAuthFailed):
        await async_call_and_propagate_config_error(fail)


@pytest.mark.asyncio
async def test_deco_coordinator_update_adds_new_deco():
    hass = _make_hass()
    api = MagicMock()
    api.async_list_devices = AsyncMock(return_value=[_master_deco_dict()])
    api.async_get_performance = AsyncMock(
        return_value={"result": {"cpu_usage": 0.42, "mem_usage": 0.55}}
    )

    coordinator = TplinkDecoUpdateCoordinator(hass, api, _make_config_entry())
    data = await coordinator._async_update_data()

    assert len(data.decos) == 1
    assert data.master_deco is not None
    assert data.master_deco.cpu_usage_raw == 42.0
    assert data.master_deco.mem_usage_raw == 55.0
    hass.loop.call_soon.assert_called_once()


@pytest.mark.asyncio
async def test_deco_coordinator_marks_missing_deco_offline():
    hass = _make_hass()
    old = TpLinkDeco("AA:BB:CC:DD:EE:02")
    old.online = True
    old.internet_online = True

    api = MagicMock()
    api.async_list_devices = AsyncMock(return_value=[_master_deco_dict()])
    api.async_get_performance = AsyncMock(return_value={"result": {}})

    coordinator = TplinkDecoUpdateCoordinator(
        hass,
        api,
        _make_config_entry(),
        data=TpLinkDecoData(decos={"AA:BB:CC:DD:EE:02": old}),
    )
    data = await coordinator._async_update_data()

    assert data.decos["AA:BB:CC:DD:EE:02"].online is False
    assert data.decos["AA:BB:CC:DD:EE:02"].internet_online is False


@pytest.mark.asyncio
async def test_deco_coordinator_paused_returns_cached_data():
    hass = _make_hass()
    api = MagicMock()
    cached = TpLinkDecoData(
        decos={"AA:BB:CC:DD:EE:01": TpLinkDeco("AA:BB:CC:DD:EE:01")}
    )

    coordinator = TplinkDecoUpdateCoordinator(
        hass, api, _make_config_entry(), data=cached
    )
    coordinator.paused = True
    data = await coordinator._async_update_data()

    assert data is cached
    api.async_list_devices.assert_not_called()


@pytest.mark.asyncio
async def test_client_coordinator_empty_decos_returns_existing():
    hass = _make_hass()
    api = MagicMock()
    deco_coord = MagicMock()
    deco_coord.paused = False
    deco_coord.data = TpLinkDecoData(decos={})

    existing = {"11:22:33:44:55:66": TpLinkDecoClient("11:22:33:44:55:66")}
    coordinator = TplinkDecoClientUpdateCoordinator(
        hass,
        api,
        _make_config_entry(),
        deco_coord,
        consider_home_seconds=180,
        data=existing,
    )

    data = await coordinator._async_update_data()
    assert data is existing
    api.async_list_clients.assert_not_called()


@pytest.mark.asyncio
async def test_client_coordinator_5xx_fallback(monkeypatch):
    hass = _make_hass()
    api = MagicMock()
    master = TpLinkDeco("AA:BB:CC:DD:EE:01")
    master.mac = "AA:BB:CC:DD:EE:01"
    slave = TpLinkDeco("AA:BB:CC:DD:EE:02")
    slave.mac = "AA:BB:CC:DD:EE:02"

    deco_coord = MagicMock()
    deco_coord.paused = False
    deco_coord.data = TpLinkDecoData(
        master_deco=master,
        decos={
            master.mac: master,
            slave.mac: slave,
        },
    )

    api.async_list_clients = AsyncMock(
        side_effect=[
            aiohttp.ClientResponseError(
                request_info=MagicMock(),
                history=(),
                status=502,
                message="Bad Gateway",
            ),
            [{"mac": "11:22:33:44:55:66", "name": "Phone", "ip": "192.168.1.5"}],
        ]
    )

    fixed_now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        "custom_components.tplink_deco.coordinator.dt_util.utcnow",
        lambda: fixed_now,
    )

    coordinator = TplinkDecoClientUpdateCoordinator(
        hass,
        api,
        _make_config_entry(),
        deco_coord,
        consider_home_seconds=180,
    )
    data = await coordinator._async_update_data()

    assert "11:22:33:44:55:66" in data
    assert data["11:22:33:44:55:66"].name == "Phone"
    assert api.async_list_clients.call_count == 2


@pytest.mark.asyncio
async def test_client_coordinator_preserves_offline_with_consider_home(monkeypatch):
    hass = _make_hass()
    api = MagicMock()
    api.async_list_clients = AsyncMock(return_value=[])

    master = TpLinkDeco("AA:BB:CC:DD:EE:01")
    deco_coord = MagicMock()
    deco_coord.paused = False
    deco_coord.data = TpLinkDecoData(master_deco=master, decos={master.mac: master})

    old_client = TpLinkDecoClient("11:22:33:44:55:66")
    old_client.last_activity = datetime(2026, 7, 11, 11, 0, tzinfo=timezone.utc)

    fixed_now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        "custom_components.tplink_deco.coordinator.dt_util.utcnow",
        lambda: fixed_now,
    )

    coordinator = TplinkDecoClientUpdateCoordinator(
        hass,
        api,
        _make_config_entry(),
        deco_coord,
        consider_home_seconds=180,
        data={"11:22:33:44:55:66": old_client},
    )
    data = await coordinator._async_update_data()

    assert data["11:22:33:44:55:66"].online is False


@pytest.mark.asyncio
async def test_coordinator_on_close():
    hass = _make_hass()
    api = MagicMock()
    coordinator = TplinkDecoUpdateCoordinator(hass, api, _make_config_entry())

    called = []

    def closer():
        called.append(True)

    coordinator.on_close(closer)
    await coordinator.async_close()
    assert called == [True]
