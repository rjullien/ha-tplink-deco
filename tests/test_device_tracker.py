"""Tests for tracker entity attributes."""

from datetime import datetime
from datetime import timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from custom_components.tplink_deco.coordinator import TpLinkDeco
from custom_components.tplink_deco.coordinator import TpLinkDecoClient
from custom_components.tplink_deco.coordinator import TpLinkDecoData
from custom_components.tplink_deco.device_tracker import TplinkDecoClientDeviceTracker
from custom_components.tplink_deco.device_tracker import TplinkDecoDeviceTracker


def _make_master_deco() -> TpLinkDeco:
    deco = TpLinkDeco("AA:BB:CC:DD:EE:01")
    deco.update(
        {
            "mac": deco.mac,
            "nickname": "living_room",
            "role": "master",
            "group_status": "connected",
            "connection_type": "wifi",
        }
    )
    return deco


def _make_deco_coordinator(deco: TpLinkDeco) -> MagicMock:
    coordinator = MagicMock()
    coordinator.data = TpLinkDecoData(master_deco=deco, decos={deco.mac: deco})
    return coordinator


def _make_client_entity(client_type: str | None = "phone"):
    deco = _make_master_deco()
    deco_coordinator = _make_deco_coordinator(deco)
    client = TpLinkDecoClient("11:22:33:44:55:66")
    client.update(
        {
            "mac": client.mac,
            "name": "Phone",
            "connection_type": "band5",
            "interface": "main",
            "client_type": client_type,
            "wire_type": "wireless",
            "client_mesh": True,
        },
        deco.mac,
        datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc),
    )
    client_coordinator = MagicMock()
    client_coordinator.data = {client.mac: client}
    entity = TplinkDecoClientDeviceTracker(
        deco_coordinator,
        client_coordinator,
        client,
        "",
        "",
        True,
    )
    return entity, client


def test_deco_extra_attributes_do_not_override_named_attributes():
    deco = _make_master_deco()
    deco.extra = {
        "connection_type": "override",
        "master": False,
        "future_field": "preserved",
    }
    entity = TplinkDecoDeviceTracker(
        _make_deco_coordinator(deco),
        deco,
        "",
        "",
    )

    attributes = entity.extra_state_attributes

    assert attributes["connection_type"] == "wifi"
    assert attributes["master"] is True
    assert attributes["future_field"] == "preserved"


def test_client_extra_attributes_do_not_override_named_attributes():
    entity, client = _make_client_entity()
    client.extra = {
        "connection_type": "override",
        "client_type": "tablet",
        "interface": "guest",
        "deco_device": "override",
        "future_field": "preserved",
    }

    attributes = entity.extra_state_attributes

    assert attributes["connection_type"] == "band5"
    assert attributes["client_type"] == "phone"
    assert attributes["interface"] == "main"
    assert attributes["deco_device"] == "Living Room"
    assert attributes["future_field"] == "preserved"


@pytest.mark.asyncio
async def test_client_type_is_restored_from_old_state(monkeypatch):
    entity, _client = _make_client_entity(client_type=None)
    monkeypatch.setattr(
        "custom_components.tplink_deco.device_tracker.CoordinatorEntity.async_added_to_hass",
        AsyncMock(),
        raising=False,
    )
    monkeypatch.setattr(
        entity,
        "async_get_last_state",
        AsyncMock(return_value=SimpleNamespace(attributes={"client_type": "tablet"})),
    )
    monkeypatch.setattr(entity, "async_write_ha_state", MagicMock())

    await entity.async_added_to_hass()

    assert entity._attr_client_type == "tablet"
    assert entity.extra_state_attributes["client_type"] == "tablet"
