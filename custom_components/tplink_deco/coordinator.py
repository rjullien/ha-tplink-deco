"""TP-Link Deco Coordinator"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
import ipaddress
import logging
from time import monotonic
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.issue_registry import IssueSeverity
from homeassistant.helpers.issue_registry import async_create_issue
from homeassistant.helpers.issue_registry import async_delete_issue
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from .api import TplinkDecoApi
from .api import _RAW_RESPONSE_SECRET_KEYS
from .api import normalize_name
from .const import DOMAIN
from .const import SIGNAL_CLIENT_ADDED
from .const import SIGNAL_DECO_ADDED
from .exceptions import LoginForbiddenException
from .exceptions import LoginInvalidException
from .exceptions import TimeoutException
from .exceptions import TransientConnectionException

_LOGGER: logging.Logger = logging.getLogger(__name__)
GLOBAL_FALLBACK_PROBE_INTERVAL_SECONDS = 300
SUSPICIOUS_CLIENT_LIST_RETRY_WINDOW = timedelta(minutes=30)
SUSPICIOUS_CLIENT_LIST_ISSUE_ID = "suspicious_client_list"
CLIENT_BACKOFF_INITIAL_SECONDS = 30
CLIENT_BACKOFF_MAX_SECONDS = 300


@dataclass
class CoordinatorHealth:
    """Runtime health details for a coordinator."""

    last_successful_update: datetime | None = None
    response_time_ms: int | None = None
    timeout_count: int = 0
    suspect_client_list_count: int = 0
    consecutive_failures: int = 0
    last_error: str = "0"

    def record_success(self, started: float) -> None:
        """Record a successful coordinator update."""
        self.last_successful_update = dt_util.utcnow()
        self.response_time_ms = round((monotonic() - started) * 1000)
        self.consecutive_failures = 0

    def record_failure(self, started: float, err: Exception) -> None:
        """Record a failed coordinator update without exposing response data."""
        self.response_time_ms = round((monotonic() - started) * 1000)
        self.consecutive_failures += 1
        self.last_error = type(err).__name__
        if isinstance(err, TimeoutException):
            self.timeout_count += 1

    def record_backoff(self, started: float, err: Exception | None = None) -> None:
        """Record coordinator backoff without marking update as successful."""
        self.response_time_ms = round((monotonic() - started) * 1000)
        self.consecutive_failures += 1
        if err is not None:
            self.last_error = type(err).__name__


def coerce_float(value):
    """Coerce numeric values returned as strings by legacy firmware."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def coerce_int(value: Any) -> int | None:
    """Coerce integer values returned as strings by Deco firmware."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _extra_fields(
    data: dict[str, Any],
    handled_fields: frozenset[str],
    *,
    scalar_lists: bool = False,
) -> dict[str, Any]:
    """Return unhandled scalar API values suitable for entity attributes."""
    return {
        key: value
        for key, value in data.items()
        if isinstance(key, str)
        and key not in handled_fields
        and key.casefold() not in _RAW_RESPONSE_SECRET_KEYS
        and (
            _is_scalar(value)
            or (
                scalar_lists
                and isinstance(value, list)
                and all(_is_scalar(item) for item in value)
            )
        )
    }


_DECO_HANDLED_FIELDS = frozenset(
    {
        "mac",
        "hardware_ver",
        "software_ver",
        "device_model",
        "custom_nickname",
        "nickname",
        "device_ip",
        "group_status",
        "inet_status",
        "role",
        "connection_type",
        "bssid_2g",
        "bssid_5g",
        "bssid_sta_2g",
        "bssid_sta_5g",
        "signal_level",
        "backhual_speed",
        "backhual_max_speed",
        "signal_strength",
        "inet_error_msg",
        "previous",
        "parent_device_id",
        "device_id",
        "easymesh_role",
        "rx_rate_list",
        "tx_rate_list",
        "wired_port_list",
    }
)

_CLIENT_HANDLED_FIELDS = frozenset(
    {
        "mac",
        "name",
        "ip",
        "online",
        "connection_type",
        "interface",
        "down_speed",
        "up_speed",
        "client_type",
        "wire_type",
        "client_mesh",
    }
)


def _summarize_wired_ports(port_list: Any) -> dict[str, dict[str, int | None]]:
    """Summarize the repeated client entries in a Deco wired-port list."""
    ports: dict[str, dict[str, int | None]] = {}
    if not isinstance(port_list, list):
        return ports

    for client in port_list:
        if not isinstance(client, dict) or client.get("port") is None:
            continue
        port = str(client["port"])
        speed = coerce_int(client.get("port_speed"))
        summary = ports.setdefault(port, {"speed": speed, "clients": 0})
        if summary["speed"] is None:
            summary["speed"] = speed
        elif speed is not None:
            summary["speed"] = min(summary["speed"], speed)
        summary["clients"] = int(summary["clients"]) + 1

    return ports


def kilobits_to_kilobytes(kilobits_count):
    """Convert kilobits to kilobytes (the Deco API reports speeds in kbit/s)."""
    numeric_value = coerce_float(kilobits_count)
    return numeric_value / 8 if numeric_value is not None else None


def filter_invalid_ip(ip_address):
    try:
        # Check that it parsed to an IP address
        ipaddress.ip_address(ip_address)
        return ip_address
    except ValueError:
        return None


def snake_case_to_title_space(str):
    return " ".join([w.title() for w in str.split("_")])


async def async_call_and_propagate_config_error(func, *args, **kwargs):
    try:
        return await func(*args, **kwargs)
    except (LoginForbiddenException, LoginInvalidException) as err:
        raise ConfigEntryAuthFailed from err


class TpLinkDeco:
    """Class to manage TP-Link Deco device."""

    def __init__(self, mac: str) -> None:
        self.mac = mac

        self.hw_version = None
        self.sw_version = None
        self.device_model = None

        self.name = None
        self.ip_address = None
        self.online = None
        self.internet_online = None
        self.master = None
        self.connection_type = None
        self.interface = None
        self.bssid_band2_4 = None
        self.bssid_band5 = None
        self.backhaul_bssid_band2_4 = None
        self.backhaul_bssid_band5 = None
        self.signal_band2_4 = None
        self.signal_band5 = None
        self.signal_band6 = None
        self.signal_strength_band2_4 = None
        self.signal_strength_band5 = None
        self.signal_strength_band6 = None
        self.internet_status_message = None
        self.parent_mac = None
        self.parent_device_id = None
        self.device_id = None
        self.easymesh_role = None
        self.rx_rate_band2_4 = None
        self.rx_rate_band5 = None
        self.tx_rate_band2_4 = None
        self.tx_rate_band5 = None
        self.wired_ports: dict[str, dict[str, int | None]] = {}
        self.wired_port_speed_min = None
        self.extra: dict[str, Any] = {}
        self.backhaul_speed = None
        self.backhaul_max_speed = None
        self.cpu_usage = None
        self.cpu_usage_raw = None
        self.mem_usage = None
        self.mem_usage_raw = None

    def update(
        self,
        data: dict[str, Any],
    ) -> None:
        self.hw_version = data.get("hardware_ver")
        self.sw_version = data.get("software_ver")
        self.device_model = data.get("device_model")

        self.name = data.get("custom_nickname")  # Only set if custom value
        if self.name is None:
            nickname = data.get("nickname")
            if nickname:
                self.name = normalize_name(snake_case_to_title_space(nickname))
        self.ip_address = filter_invalid_ip(data.get("device_ip"))
        self.online = data.get("group_status") == "connected"
        inet = data.get("inet_status")
        if inet is None:
            self.internet_online = None
        elif isinstance(inet, str):
            self.internet_online = inet.lower() in ("online", "connected", "up")
        else:
            self.internet_online = bool(inet)
        self.master = data.get("role") == "master"
        self.connection_type = data.get("connection_type")
        self.bssid_band2_4 = data.get("bssid_2g")
        self.bssid_band5 = data.get("bssid_5g")
        self.backhaul_bssid_band2_4 = data.get("bssid_sta_2g")
        self.backhaul_bssid_band5 = data.get("bssid_sta_5g")
        signal_level = data.get("signal_level")
        if not isinstance(signal_level, dict):
            signal_level = {}
        self.signal_band2_4 = signal_level.get("band2_4")
        self.signal_band5 = signal_level.get("band5")
        self.signal_band6 = signal_level.get("band6")
        signal_strength = data.get("signal_strength")
        if not isinstance(signal_strength, dict):
            signal_strength = {}
        self.signal_strength_band2_4 = coerce_int(signal_strength.get("band2_4"))
        self.signal_strength_band5 = coerce_int(signal_strength.get("band5"))
        self.signal_strength_band6 = coerce_int(signal_strength.get("band6"))
        self.internet_status_message = data.get("inet_error_msg")
        self.parent_mac = data.get("previous") or None
        self.parent_device_id = data.get("parent_device_id")
        self.device_id = data.get("device_id")
        self.easymesh_role = data.get("easymesh_role")
        rx_rates = data.get("rx_rate_list")
        if not isinstance(rx_rates, dict):
            rx_rates = {}
        tx_rates = data.get("tx_rate_list")
        if not isinstance(tx_rates, dict):
            tx_rates = {}
        self.rx_rate_band2_4 = rx_rates.get("band2_4")
        self.rx_rate_band5 = rx_rates.get("band5")
        self.tx_rate_band2_4 = tx_rates.get("band2_4")
        self.tx_rate_band5 = tx_rates.get("band5")
        self.wired_ports = _summarize_wired_ports(data.get("wired_port_list"))
        speeds = [
            port["speed"]
            for port in self.wired_ports.values()
            if isinstance(port["speed"], int) and not isinstance(port["speed"], bool)
        ]
        self.wired_port_speed_min = min(speeds) if speeds else None
        self.extra = _extra_fields(data, _DECO_HANDLED_FIELDS, scalar_lists=True)
        self.backhaul_speed = data.get("backhual_speed")
        self.backhaul_max_speed = data.get("backhual_max_speed")


class TpLinkDecoClient:
    """Class to manage TP-Link Deco Client."""

    def __init__(self, mac: str) -> None:
        self.mac = mac
        self.name = None
        self.ip_address = None
        self.online = False
        self.connection_type = None
        self.interface = None
        self.client_type = None
        self.wire_type = None
        self.client_mesh = None
        self.down_kilobytes_per_s = 0
        self.up_kilobytes_per_s = 0
        self.deco_mac = None
        self.last_activity = None
        self.extra: dict[str, Any] = {}

    def update(
        self,
        data: dict[str, Any],
        deco_mac: str,
        utc_point_in_time: datetime,
    ) -> None:
        self.deco_mac = deco_mac
        self.name = data.get("name")
        self.ip_address = filter_invalid_ip(data.get("ip"))
        # client_list only returns connected clients, so a listed client is
        # online even if the firmware omits the "online" field.
        self.online = bool(data.get("online", True))
        self.connection_type = data.get("connection_type")
        self.interface = data.get("interface")
        self.client_type = data.get("client_type")
        self.wire_type = data.get("wire_type")
        self.client_mesh = data.get("client_mesh")
        self.down_kilobytes_per_s = kilobits_to_kilobytes(data.get("down_speed", 0))
        self.up_kilobytes_per_s = kilobits_to_kilobytes(data.get("up_speed", 0))
        self.last_activity = utc_point_in_time
        self.extra = _extra_fields(data, _CLIENT_HANDLED_FIELDS)


class TpLinkDecoData:
    """Class for coordinator data."""

    def __init__(
        self,
        master_deco: TpLinkDeco = None,
        decos: dict[str, TpLinkDeco] = None,
    ) -> None:
        self.master_deco = master_deco
        self.decos = {} if decos is None else decos


class TplinkDecoUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: TplinkDecoApi,
        config_entry: ConfigEntry,
        update_interval: timedelta = None,
        data: TpLinkDecoData = None,
        device_list_interval_seconds: int = 30,
    ) -> None:
        """Initialize."""
        self.api = api
        self._on_close: list[Callable] = []
        self.device_list_interval_seconds = device_list_interval_seconds
        self._last_device_list_update: float | None = None
        self._force_device_list_refresh = False

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN}-decos",
            update_interval=update_interval,
        )
        # Must happen after super().__init__
        self.data = TpLinkDecoData() if data is None else data

        self.paused = False
        self.health = CoordinatorHealth()

    async def _async_update_data(self):
        """Update data via api."""
        if self.paused and not self._force_device_list_refresh:
            _LOGGER.debug("Deco polling is paused")
            return self.data

        started = monotonic()
        try:
            data = await self._async_update_data_internal()
        except Exception as err:
            self.health.record_failure(started, err)
            # DataUpdateCoordinator only notifies listeners on the first
            # transition to failure. Publish health changes during a sustained
            # outage as well, without duplicating that first notification.
            if not self.last_update_success:
                self.async_update_listeners()
            raise

        self.health.record_success(started)
        return data

    async def _async_update_data_internal(self):
        """Fetch and process Deco data."""

        if self._device_list_refresh_due():
            device_list_started = monotonic()
            _LOGGER.debug("device_list request started")
            try:
                new_decos = await async_call_and_propagate_config_error(
                    self.api.async_list_devices
                )
            except Exception:
                _LOGGER.debug(
                    "device_list request failed duration_seconds=%.3f",
                    monotonic() - device_list_started,
                )
                raise
            self._process_device_list(new_decos)
            self._last_device_list_update = monotonic()
            self._force_device_list_refresh = False
            _LOGGER.debug(
                "device_list request completed duration_seconds=%.3f",
                monotonic() - device_list_started,
            )
        else:
            _LOGGER.debug("device_list request skipped")

        performance_started = monotonic()
        _LOGGER.debug("performance request started")
        # CPU/memory is diagnostic-only data: some firmwares do not expose the
        # performance endpoint at all, and others fail it while under load.
        # Losing it must not invalidate the mesh refresh, which the device
        # trackers and every other entity depend on. Auth failures still
        # propagate so Home Assistant can start the reauth flow.
        performance_data = None
        try:
            performance_data = await async_call_and_propagate_config_error(
                self.api.async_get_performance
            )
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            _LOGGER.debug(
                "performance request failed duration_seconds=%.3f; "
                "retaining previous values: %s",
                monotonic() - performance_started,
                err,
            )
        else:
            _LOGGER.debug(
                "performance request completed duration_seconds=%.3f",
                monotonic() - performance_started,
            )

        # Zet globale performance data op de master Deco.
        # When the performance call failed, result stays empty so the existing
        # cpu_usage/mem_usage values are left untouched instead of being reset.
        result = performance_data.get("result", {}) if performance_data else {}
        master_deco = self.data.master_deco
        if master_deco is not None:
            cpu_raw = result.get("cpu_usage")
            mem_raw = result.get("mem_usage")

            cpu_value = coerce_float(cpu_raw)
            if cpu_value is not None:
                cpu_percent = cpu_value * 100
                master_deco.cpu_usage_raw = round(cpu_percent, 1)

                if master_deco.cpu_usage is not None:
                    master_deco.cpu_usage = round(
                        (master_deco.cpu_usage * 0.7) + (cpu_percent * 0.3), 1
                    )
                else:
                    master_deco.cpu_usage = round(cpu_percent, 1)

            mem_value = coerce_float(mem_raw)
            if mem_value is not None:
                mem_percent = mem_value * 100
                master_deco.mem_usage_raw = round(mem_percent, 1)

                if master_deco.mem_usage is not None:
                    master_deco.mem_usage = round(
                        (master_deco.mem_usage * 0.7) + (mem_percent * 0.3), 1
                    )
                else:
                    master_deco.mem_usage = round(mem_percent, 1)

        return self.data

    def _device_list_refresh_due(self) -> bool:
        """Return whether device_list should be refreshed this cycle."""
        if self._force_device_list_refresh or self._last_device_list_update is None:
            return True
        if self.device_list_interval_seconds == 0:
            return False
        return (
            monotonic() - self._last_device_list_update
            >= self.device_list_interval_seconds
        )

    def _process_device_list(self, new_decos: list[dict[str, Any]]) -> None:
        """Update cached Deco data from a device_list response."""
        old_decos = self.data.decos
        master_deco = None
        deco_added = False
        decos = {}
        for new_deco in new_decos:
            mac = new_deco["mac"]
            deco = old_decos.get(mac)
            if deco is None:
                deco_added = True
                deco = TpLinkDeco(mac)
                _LOGGER.debug("_async_update_data: Found new deco mac=%s", deco.mac)
            deco.update(new_deco)
            decos[mac] = deco
            if deco.master:
                master_deco = deco

        for mac, old_deco in old_decos.items():
            if mac not in decos:
                _LOGGER.debug(
                    "_async_update_data: Deco mac=%s not returned by API, marking offline",
                    mac,
                )
                old_deco.online = False
                old_deco.internet_online = False
                decos[mac] = old_deco

        if deco_added:
            # Defer the dispatch until after the coordinator has committed
            # the new data. async_dispatcher_send runs @callback listeners
            # synchronously, so dispatching here would make them iterate the
            # *old* coordinator data, and the new deco would never get its
            # entities (the signal only fires once per discovery).
            self.hass.loop.call_soon(
                async_dispatcher_send, self.hass, SIGNAL_DECO_ADDED
            )

        self.data = TpLinkDecoData(master_deco, decos)

    async def async_request_device_refresh(self) -> None:
        """Request an immediate device_list refresh."""
        self._force_device_list_refresh = True
        await self.async_request_refresh()

    @callback
    def on_close(self, func: CALLBACK_TYPE) -> None:
        """Add a function to call when coordinator is closed."""
        self._on_close.append(func)

    async def async_close(self) -> None:
        """Call functions on close."""
        for func in self._on_close:
            try:
                func()
            except Exception as err:
                _LOGGER.error("Error calling on_close function %s: %s", func, err)
        self._on_close.clear()


class TplinkDecoClientUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: TplinkDecoApi,
        config_entry: ConfigEntry,
        deco_update_coordinator: TplinkDecoUpdateCoordinator,
        consider_home_seconds: int,
        update_interval: timedelta = None,
        data: dict[str, TpLinkDecoClient] = None,
    ) -> None:
        """Initialize."""
        self.api = api
        self._deco_update_coordinator = deco_update_coordinator
        self._consider_home_seconds = consider_home_seconds
        self._on_close: list[Callable] = []

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN}-clients",
            update_interval=update_interval,
        )
        # Must happen after super().__init__
        self.data = {} if data is None else data
        self._suspicious_client_list_issue_id = (
            f"{SUSPICIOUS_CLIENT_LIST_ISSUE_ID}_{config_entry.entry_id}"
        )
        self.has_successful_refresh = False
        self._use_global_client_query = False
        self._next_per_node_probe = 0.0
        self._client_backoff_until = 0.0
        self._client_backoff_seconds = 0.0
        self._last_logged_500_error: str | None = None
        self.health = CoordinatorHealth()
        self._suspicious_client_list_since: datetime | None = None
        self._suspicious_baseline: int | None = None
        self._suspicious_client_list_issue_open = False

    @property
    def client_query_mode(self) -> str:
        """Return the client query strategy currently in use."""
        return "global_fallback" if self._use_global_client_query else "per_node"

    @property
    def is_backed_off(self) -> bool:
        """Return whether client polling is currently backed off."""
        return monotonic() < self._client_backoff_until

    @property
    def remaining_backoff_seconds(self) -> int:
        """Return the remaining backoff time in seconds."""
        remaining = self._client_backoff_until - monotonic()
        return max(0, int(round(remaining)))

    def _apply_client_backoff(
        self, err: Exception, started: float | None = None
    ) -> None:
        """Apply capped exponential backoff on HTTP 500 response."""
        if self._client_backoff_seconds <= 0.0:
            self._client_backoff_seconds = float(CLIENT_BACKOFF_INITIAL_SECONDS)
        else:
            self._client_backoff_seconds = min(
                self._client_backoff_seconds * 2,
                float(CLIENT_BACKOFF_MAX_SECONDS),
            )
        self._client_backoff_until = monotonic() + self._client_backoff_seconds

        status = getattr(err, "status", 500)
        message = getattr(err, "message", "Internal Server Error")
        error_key = f"{status}_{message}"

        if self._last_logged_500_error != error_key:
            _LOGGER.warning(
                "Client list query returned HTTP %s (%s); backing off for %d seconds and preserving client states",
                status,
                message,
                int(self._client_backoff_seconds),
            )
            self._last_logged_500_error = error_key
        else:
            _LOGGER.debug(
                "Client list query returned HTTP %s (%s); backing off for %d seconds",
                status,
                message,
                int(self._client_backoff_seconds),
            )

        if started is not None:
            self.health.record_backoff(started, err)

    def _reset_client_backoff(self) -> None:
        """Reset exponential backoff after a successful response."""
        if self._client_backoff_seconds > 0.0:
            _LOGGER.info("Client list query recovered after HTTP 500 backoff")
        self._client_backoff_seconds = 0.0
        self._client_backoff_until = 0.0
        self._last_logged_500_error = None

    async def _async_list_clients_per_deco(self, deco_macs: list[str]):
        """List clients per Deco without failing the complete refresh."""
        responses = []
        failed_deco_macs = set()
        for deco_mac in deco_macs:
            try:
                response = await async_call_and_propagate_config_error(
                    self.api.async_list_clients,
                    deco_mac,
                    timeout_error_retries=0,
                )
            except aiohttp.ClientResponseError as err:
                if err.status < 500:
                    raise
                failed_deco_macs.add(deco_mac)
                _LOGGER.debug("Per-node client_list failed for %s: %s", deco_mac, err)
            except TimeoutException as err:
                self.health.timeout_count += 1
                failed_deco_macs.add(deco_mac)
                _LOGGER.debug(
                    "Per-node client_list timed out for %s: %s", deco_mac, err
                )
            except TransientConnectionException as err:
                failed_deco_macs.add(deco_mac)
                _LOGGER.debug(
                    "Per-node client_list connection failed for %s after retries: %s",
                    deco_mac,
                    err,
                )
            else:
                responses.append((deco_mac, response))

        return responses, failed_deco_macs

    async def _async_list_clients_global(self):
        """List all clients once without timeout retries."""
        master_deco = self._deco_update_coordinator.data.master_deco
        deco_macs = [master_deco.mac if master_deco is not None else "default"]
        responses = [
            await async_call_and_propagate_config_error(
                self.api.async_list_clients,
                timeout_error_retries=0,
            )
        ]
        return deco_macs, responses

    async def _async_update_data(self):
        """Update data via api."""
        if self._deco_update_coordinator.paused:
            _LOGGER.debug("Deco client polling is paused")
            return self.data

        started = monotonic()
        try:
            data = await self._async_update_data_internal(started)
        except Exception as err:
            self.health.record_failure(started, err)
            # DataUpdateCoordinator only notifies listeners on the first
            # transition to failure. Publish health changes during a sustained
            # outage as well, without duplicating that first notification.
            if not self.last_update_success:
                self.async_update_listeners()
            raise

        if not self.is_backed_off:
            self.health.record_success(started)
        return data

    async def _async_update_data_internal(self, started: float | None = None):
        """Fetch and process client data."""
        if len(self._deco_update_coordinator.data.decos) == 0:
            # Return the existing data instead of None: returning None would
            # replace self.data and crash the next cycle and every sensor
            # that iterates self.coordinator.data.values().
            return self.data
        if self.is_backed_off:
            _LOGGER.debug(
                "Client polling is backed off until %.1f (%ds remaining); preserving previous client states",
                self._client_backoff_until,
                self.remaining_backoff_seconds,
            )
            return self.data

        old_clients = self.data
        clients = {}
        client_added = False
        # List clients for all decos if _deco_update_coordinator is not provided
        deco_macs = list(self._deco_update_coordinator.data.decos)
        utc_point_in_time = dt_util.utcnow()

        failed_deco_macs = set()
        per_node_results = False
        should_try_per_node = (
            not self._use_global_client_query
            or monotonic() >= self._next_per_node_probe
        )

        server_500_error = None
        if should_try_per_node:
            (
                deco_client_responses,
                failed_deco_macs,
            ) = await self._async_list_clients_per_deco(deco_macs)
            if deco_client_responses:
                per_node_results = True
                if self._use_global_client_query:
                    _LOGGER.info(
                        "Per-node client_list recovered; leaving global fallback"
                    )
                self._use_global_client_query = False
            else:
                self._use_global_client_query = True
                self._next_per_node_probe = (
                    monotonic() + GLOBAL_FALLBACK_PROBE_INTERVAL_SECONDS
                )
                _LOGGER.debug(
                    "All per-node client_list queries failed; using global fallback"
                )
                try:
                    deco_macs, responses = await self._async_list_clients_global()
                    deco_client_responses = list(zip(deco_macs, responses))
                    failed_deco_macs.clear()
                except aiohttp.ClientResponseError as err:
                    if err.status < 500:
                        raise
                    server_500_error = err
                    deco_client_responses = []
        else:
            try:
                deco_macs, responses = await self._async_list_clients_global()
                deco_client_responses = list(zip(deco_macs, responses))
            except aiohttp.ClientResponseError as err:
                if err.status < 500:
                    raise
                server_500_error = err
                deco_client_responses = []

        if server_500_error is not None:
            self._apply_client_backoff(server_500_error, started)
            return self.data

        self._reset_client_backoff()

        if per_node_results:
            for deco_mac, deco_clients in deco_client_responses:
                if (
                    deco_clients is not None
                    and not deco_clients
                    and sum(
                        client.online and client.deco_mac == deco_mac
                        for client in old_clients.values()
                    )
                    >= 3
                ):
                    failed_deco_macs.add(deco_mac)

        prev_online = sum(client.online for client in old_clients.values())
        new_total = sum(
            len(deco_clients or []) for _deco_mac, deco_clients in deco_client_responses
        )
        suspicious_client_list = prev_online >= 10 and new_total < 0.2 * prev_online
        if self._suspicious_client_list_issue_open:
            baseline = self._suspicious_baseline or prev_online
            if new_total >= 0.2 * baseline:
                async_delete_issue(
                    self.hass,
                    DOMAIN,
                    self._suspicious_client_list_issue_id,
                )
                self._suspicious_client_list_issue_open = False
                self._suspicious_client_list_since = None
                self._suspicious_baseline = None
                suspicious_client_list = False

        if suspicious_client_list:
            self.health.suspect_client_list_count += 1
            if self._suspicious_client_list_since is None:
                self._suspicious_client_list_since = utc_point_in_time
                self._suspicious_baseline = prev_online
            elif self._suspicious_baseline is None:
                self._suspicious_baseline = prev_online
            baseline = self._suspicious_baseline

            if (
                utc_point_in_time - self._suspicious_client_list_since
                >= SUSPICIOUS_CLIENT_LIST_RETRY_WINDOW
            ):
                _LOGGER.warning(
                    "Suspicious client list persisted for 30 minutes "
                    "(%d clients vs %d online before); accepting current list",
                    new_total,
                    prev_online,
                )
                if not self._suspicious_client_list_issue_open:
                    async_create_issue(
                        self.hass,
                        DOMAIN,
                        self._suspicious_client_list_issue_id,
                        is_fixable=False,
                        severity=IssueSeverity.WARNING,
                        translation_key=SUSPICIOUS_CLIENT_LIST_ISSUE_ID,
                    )
                    self._suspicious_client_list_issue_open = True
                failed_deco_macs.clear()
            else:
                _LOGGER.warning(
                    "Suspicious client list (%d clients vs %d online before); "
                    "retrying once",
                    new_total,
                    prev_online,
                )
                try:
                    deco_macs, retry_responses = await self._async_list_clients_global()
                except aiohttp.ClientResponseError as err:
                    if err.status < 500:
                        raise
                    self._apply_client_backoff(err, started)
                    return self.data
                retry_client_responses = list(zip(deco_macs, retry_responses))
                retry_total = sum(
                    len(deco_clients or [])
                    for _deco_mac, deco_clients in retry_client_responses
                )
                if retry_total < 0.2 * baseline:
                    raise UpdateFailed(
                        f"Suspicious client list: {retry_total} clients vs "
                        f"{baseline} online before"
                    )
                deco_client_responses = retry_client_responses
                failed_deco_macs.clear()
                self._suspicious_client_list_since = None
                self._suspicious_baseline = None
        else:
            if not self._suspicious_client_list_issue_open:
                self._suspicious_client_list_since = None
                self._suspicious_baseline = None

        if len(deco_client_responses) > 0:
            for deco_mac, deco_clients in deco_client_responses:
                if deco_clients is None:
                    continue  # Skip failed deco queries
                for deco_client in deco_clients:
                    client_mac = deco_client["mac"]
                    client = old_clients.get(client_mac)
                    if client is None:
                        client_added = True
                        client = TpLinkDecoClient(client_mac)
                        _LOGGER.debug(
                            "_async_update_data: Found new client mac=%s", client.mac
                        )
                    client.update(deco_client, deco_mac, utc_point_in_time)
                    clients[client_mac] = client

        # Copy over clients no longer online
        for client in old_clients.values():
            mac = client.mac
            if mac not in clients:
                clients[mac] = client
                # Retain last-known presence for clients on Decos that failed
                # this cycle (transient per-node outage); otherwise apply
                # consider_home.
                if client.deco_mac in failed_deco_macs:
                    continue
                if client.last_activity is None:
                    client.online = False
                else:
                    client.online = (
                        utc_point_in_time - client.last_activity
                    ).total_seconds() < self._consider_home_seconds

        if client_added:
            # See TplinkDecoUpdateCoordinator: defer until data is committed.
            self.hass.loop.call_soon(
                async_dispatcher_send, self.hass, SIGNAL_CLIENT_ADDED
            )

        self.has_successful_refresh = True
        return clients

    @callback
    def on_close(self, func: CALLBACK_TYPE) -> None:
        """Add a function to call when coordinator is closed."""
        self._on_close.append(func)

    async def async_close(self) -> None:
        """Call functions on close."""
        for func in self._on_close:
            try:
                func()
            except Exception as err:
                _LOGGER.error("Error calling on_close function %s: %s", func, err)
        self._on_close.clear()
