"""Diagnostics support for TP-Link Deco."""

from datetime import datetime
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.const import CONF_PASSWORD
from homeassistant.const import CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import COORDINATOR_CLIENTS_KEY
from .const import COORDINATOR_DECOS_KEY
from .const import DOMAIN
from .coordinator import TpLinkDeco
from .coordinator import TpLinkDecoClient
from .coordinator import TplinkDecoClientUpdateCoordinator
from .coordinator import TplinkDecoUpdateCoordinator

TO_REDACT = {
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    "access_token",
    "access_host",
    "cookie",
    "default_ssid",
    "device_id",
    "device_ip",
    "hw_id",
    "ip",
    "mac",
    "oem_id",
    "owner_id",
    "parent_device_id",
    "parent_mac",
    "previous",
    "refresh_token",
    "secret",
    "session",
    "session_id",
    "space_id",
    "stok",
    "token",
}


def _coordinator_diagnostics(coordinator) -> dict[str, Any]:
    """Return non-sensitive coordinator state."""
    update_interval = coordinator.update_interval
    health = coordinator.health
    return {
        "last_update_success": coordinator.last_update_success,
        "last_successful_update": (
            health.last_successful_update.isoformat()
            if health.last_successful_update is not None
            else None
        ),
        "response_time_ms": health.response_time_ms,
        "timeout_count": health.timeout_count,
        "suspect_client_list_count": health.suspect_client_list_count,
        "consecutive_failures": health.consecutive_failures,
        "last_error": health.last_error,
        "update_interval_seconds": (
            update_interval.total_seconds() if update_interval is not None else None
        ),
    }


def _deco_diagnostics(deco: TpLinkDeco, identifier: str) -> dict[str, Any]:
    """Return diagnostics for a Deco without personal identifiers."""
    return async_redact_data(
        {
            "id": identifier,
            "device_model": deco.device_model,
            "hardware_version": deco.hw_version,
            "software_version": deco.sw_version,
            "online": deco.online,
            "internet_online": deco.internet_online,
            "master": deco.master,
            "connection_type": deco.connection_type,
            "interface": deco.interface,
            "signal_2_4_ghz": deco.signal_band2_4,
            "signal_5_ghz": deco.signal_band5,
            "signal_6_ghz": deco.signal_band6,
            "signal_strength_2_4_ghz": deco.signal_strength_band2_4,
            "signal_strength_5_ghz": deco.signal_strength_band5,
            "signal_strength_6_ghz": deco.signal_strength_band6,
            "internet_status_message": deco.internet_status_message,
            "parent_mac": deco.parent_mac,
            "parent_device_id": deco.parent_device_id,
            "device_id": deco.device_id,
            "easymesh_role": deco.easymesh_role,
            "rx_rate_band2_4": deco.rx_rate_band2_4,
            "rx_rate_band5": deco.rx_rate_band5,
            "tx_rate_band2_4": deco.tx_rate_band2_4,
            "tx_rate_band5": deco.tx_rate_band5,
            "wired_ports": deco.wired_ports,
            "wired_port_speed_min": deco.wired_port_speed_min,
            "backhaul_speed": deco.backhaul_speed,
            "backhaul_max_speed": deco.backhaul_max_speed,
            "cpu_usage": deco.cpu_usage,
            "cpu_usage_raw": deco.cpu_usage_raw,
            "memory_usage": deco.mem_usage,
            "memory_usage_raw": deco.mem_usage_raw,
            "extra": deco.extra,
        },
        TO_REDACT,
    )


def _client_diagnostics(
    client: TpLinkDecoClient,
    identifier: str,
    deco_ids: dict[str, str],
) -> dict[str, Any]:
    """Return diagnostics for a client without personal identifiers."""
    last_activity: datetime | None = client.last_activity
    return async_redact_data(
        {
            "id": identifier,
            "deco_id": deco_ids.get(client.deco_mac, "unassigned"),
            "online": client.online,
            "connection_type": client.connection_type,
            "interface": client.interface,
            "client_type": client.client_type,
            "wire_type": client.wire_type,
            "client_mesh": client.client_mesh,
            "down_kilobytes_per_s": client.down_kilobytes_per_s,
            "up_kilobytes_per_s": client.up_kilobytes_per_s,
            "last_activity": last_activity.isoformat() if last_activity else None,
            "extra": client.extra,
        },
        TO_REDACT,
    )


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    deco_coordinator: TplinkDecoUpdateCoordinator = data[COORDINATOR_DECOS_KEY]
    client_coordinator: TplinkDecoClientUpdateCoordinator = data[
        COORDINATOR_CLIENTS_KEY
    ]

    decos = sorted(deco_coordinator.data.decos.items())
    clients = sorted(client_coordinator.data.items())
    deco_ids = {mac: f"deco_{index}" for index, (mac, _) in enumerate(decos, 1)}

    return {
        "config_entry": {
            "version": config_entry.version,
            "minor_version": config_entry.minor_version,
            "data": async_redact_data(config_entry.data, TO_REDACT),
            "options": async_redact_data(config_entry.options, TO_REDACT),
        },
        "deco_coordinator": {
            **_coordinator_diagnostics(deco_coordinator),
            "paused": deco_coordinator.paused,
            "device_list_interval_seconds": (
                deco_coordinator.device_list_interval_seconds
            ),
            "master_deco_id": (
                deco_ids.get(deco_coordinator.data.master_deco.mac)
                if deco_coordinator.data.master_deco is not None
                else None
            ),
            "decos": [_deco_diagnostics(deco, deco_ids[mac]) for mac, deco in decos],
        },
        "client_coordinator": {
            **_coordinator_diagnostics(client_coordinator),
            "query_mode": client_coordinator.client_query_mode,
            "backoff_remaining_seconds": client_coordinator.remaining_backoff_seconds,
            "clients": [
                _client_diagnostics(client, f"client_{index}", deco_ids)
                for index, (_, client) in enumerate(clients, 1)
            ],
        },
    }
