"""Tests for diagnostic data redaction."""

from types import SimpleNamespace

import pytest

from custom_components.tplink_deco.const import COORDINATOR_CLIENTS_KEY
from custom_components.tplink_deco.const import COORDINATOR_DECOS_KEY
from custom_components.tplink_deco.const import COORDINATOR_MOBILE_KEY
from custom_components.tplink_deco.const import COORDINATOR_WIRELESS_KEY
from custom_components.tplink_deco.const import DOMAIN
from custom_components.tplink_deco.coordinator import TpLinkDecoData
from custom_components.tplink_deco.diagnostics import async_get_config_entry_diagnostics


def _health():
    return SimpleNamespace(
        last_successful_update=None,
        response_time_ms=None,
        timeout_count=0,
        suspect_client_list_count=0,
        consecutive_failures=0,
        last_error=None,
    )


@pytest.mark.asyncio
async def test_wireless_diagnostics_omit_ssids_and_passwords():
    ssid = "private-network-name"
    password = "private-wireless-password"
    deco_coordinator = SimpleNamespace(
        data=TpLinkDecoData(),
        health=_health(),
        last_update_success=True,
        update_interval=None,
        paused=False,
        device_list_interval_seconds=30,
    )
    client_coordinator = SimpleNamespace(
        data={},
        health=_health(),
        last_update_success=True,
        update_interval=None,
        client_query_mode="per_node",
        remaining_backoff_seconds=0,
    )
    wireless_coordinator = SimpleNamespace(
        data={"main": True},
        ssids={"main": {"band2_4": ssid}},
        raw_payload={"ssid": ssid, "password": password, "psk": password},
        last_update_success=True,
        update_interval=None,
        retry_remaining_seconds=0,
    )
    mobile_coordinator = SimpleNamespace(
        data=None,
        last_update_success=True,
        update_interval=None,
    )
    hass = SimpleNamespace(
        data={
            DOMAIN: {
                "entry": {
                    COORDINATOR_DECOS_KEY: deco_coordinator,
                    COORDINATOR_CLIENTS_KEY: client_coordinator,
                    COORDINATOR_WIRELESS_KEY: wireless_coordinator,
                    COORDINATOR_MOBILE_KEY: mobile_coordinator,
                }
            }
        }
    )
    config_entry = SimpleNamespace(
        entry_id="entry",
        version=1,
        minor_version=1,
        data={},
        options={},
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)
    serialized = repr(diagnostics)

    assert diagnostics["wireless_coordinator"]["available_networks"] == ["main"]
    assert "ssids" not in diagnostics["wireless_coordinator"]
    assert ssid not in serialized
    assert password not in serialized
