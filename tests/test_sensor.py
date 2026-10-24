"""Tests for sensor entity setup."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.tplink_deco.const import COORDINATOR_CLIENTS_KEY
from custom_components.tplink_deco.const import COORDINATOR_DECOS_KEY
from custom_components.tplink_deco.const import DOMAIN
from custom_components.tplink_deco.coordinator import TpLinkDeco
from custom_components.tplink_deco.coordinator import TpLinkDecoData
from custom_components.tplink_deco.sensor import TplinkDecoDiagnosticSensor
from custom_components.tplink_deco.sensor import async_setup_entry


@pytest.mark.asyncio
async def test_diagnostic_sensors_are_added_when_values_arrive_later():
    mac = "AA:BB:CC:DD:EE:01"
    deco = TpLinkDeco(mac)
    initial_data = {
        "mac": mac,
        "nickname": "Router",
        "role": "master",
        "group_status": "connected",
        "device_ip": "192.0.2.1",
    }
    deco.update(initial_data)

    coordinator_decos = MagicMock()
    coordinator_decos.data = TpLinkDecoData(master_deco=deco, decos={mac: deco})
    deco_listeners = []
    coordinator_decos.async_add_listener.side_effect = (
        lambda listener: deco_listeners.append(listener) or (lambda: None)
    )

    coordinator_clients = MagicMock()
    coordinator_clients.data = {}
    coordinator_clients.has_successful_refresh = False

    entry_id = "test_entry"
    hass = SimpleNamespace(
        data={
            DOMAIN: {
                entry_id: {
                    COORDINATOR_DECOS_KEY: coordinator_decos,
                    COORDINATOR_CLIENTS_KEY: coordinator_clients,
                }
            }
        }
    )
    added_entities = []

    def add_entities(entities):
        added_entities.extend(entities)

    await async_setup_entry(hass, SimpleNamespace(entry_id=entry_id), add_entities)

    def diagnostic_entities():
        return [
            entity
            for entity in added_entities
            if isinstance(entity, TplinkDecoDiagnosticSensor)
        ]

    initial_by_key = {
        entity.entity_description.key: entity for entity in diagnostic_entities()
    }
    assert "ip_address" in initial_by_key
    assert "signal_strength_2_4ghz" not in initial_by_key
    assert "signal_strength_5ghz" not in initial_by_key
    assert "wired_port_speed_min" not in initial_by_key

    deco.update(
        {
            **initial_data,
            "signal_strength": {"band2_4": "-51", "band5": -62},
            "wired_port_list": [{"port": 1, "port_speed": 1000}],
        }
    )
    deco_listeners[0]()

    updated_by_key = {
        entity.entity_description.key: entity for entity in diagnostic_entities()
    }
    assert updated_by_key["ip_address"] is initial_by_key["ip_address"]
    assert updated_by_key["signal_strength_2_4ghz"].native_value == -51
    assert updated_by_key["signal_strength_5ghz"].native_value == -62
    assert updated_by_key["wired_port_speed_min"].native_value == 1000

    deco_listeners[0]()
    keys = [entity.entity_description.key for entity in diagnostic_entities()]
    assert keys.count("ip_address") == 1
    assert keys.count("signal_strength_2_4ghz") == 1
    assert keys.count("signal_strength_5ghz") == 1
    assert keys.count("wired_port_speed_min") == 1
