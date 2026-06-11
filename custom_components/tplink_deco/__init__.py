"""
Custom integration to integrate TP-Link Deco with Home Assistant.

For more details about this integration, please refer to
https://github.com/amosyuen/ha-tplink-deco
"""

from datetime import timedelta
import logging
from typing import Any
from typing import cast

from homeassistant.components.device_tracker.const import (
    DOMAIN as DEVICE_TRACKER_DOMAIN,
)
from homeassistant.components.device_tracker.const import CONF_CONSIDER_HOME
from homeassistant.components.device_tracker.const import CONF_SCAN_INTERVAL
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.const import CONF_HOST
from homeassistant.const import CONF_PASSWORD
from homeassistant.const import CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry
from homeassistant.helpers import entity_registry
from homeassistant.helpers import restore_state
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .api import TplinkDecoApi
from .const import ATTR_DEVICE_TYPE
from .const import CONF_CLIENT_POSTFIX
from .const import CONF_CLIENT_PREFIX
from .const import CONF_DECO_POSTFIX
from .const import CONF_DECO_PREFIX
from .const import CONF_TIMEOUT_ERROR_RETRIES
from .const import CONF_TIMEOUT_SECONDS
from .const import CONF_VERIFY_SSL
from .const import COORDINATOR_CLIENTS_KEY
from .const import COORDINATOR_DECOS_KEY
from .const import DEFAULT_CONSIDER_HOME
from .const import DEFAULT_DECO_POSTFIX
from .const import DEFAULT_SCAN_INTERVAL
from .const import DEFAULT_TIMEOUT_ERROR_RETRIES
from .const import DEFAULT_TIMEOUT_SECONDS
from .const import DEVICE_TYPE_DECO
from .const import DOMAIN
from .const import PLATFORMS
from .const import SERVICE_PAUSE_POLLING
from .const import SERVICE_REBOOT_DECO
from .const import SERVICE_RESUME_POLLING
from .coordinator import TpLinkDeco
from .coordinator import TpLinkDecoClient
from .coordinator import TpLinkDecoData
from .coordinator import TplinkDecoClientUpdateCoordinator
from .coordinator import TplinkDecoUpdateCoordinator

_LOGGER: logging.Logger = logging.getLogger(__name__)


async def async_create_and_refresh_coordinators(
    hass: HomeAssistant,
    config_data: dict[str, Any],
    config_entry: ConfigEntry,
    consider_home_seconds=1,
    update_interval: timedelta = None,
    deco_data: TpLinkDecoData = None,
    client_data: dict[str, TpLinkDecoClient] = None,
):
    api = create_api(hass, config_data)
    deco_coordinator = TplinkDecoUpdateCoordinator(
        hass, api, config_entry, update_interval, deco_data
    )
    await deco_coordinator.async_config_entry_first_refresh()
    clients_coordinator = TplinkDecoClientUpdateCoordinator(
        hass,
        api,
        config_entry,
        deco_coordinator,
        consider_home_seconds,
        update_interval,
        client_data,
    )
    await clients_coordinator.async_config_entry_first_refresh()

    return {
        COORDINATOR_DECOS_KEY: deco_coordinator,
        COORDINATOR_CLIENTS_KEY: clients_coordinator,
    }


def create_api(hass: HomeAssistant, config_data: dict[str, Any]) -> TplinkDecoApi:
    """Create a TplinkDecoApi from config data."""
    return TplinkDecoApi(
        async_get_clientsession(hass),
        config_data.get(CONF_HOST),
        config_data.get(CONF_USERNAME),
        config_data.get(CONF_PASSWORD),
        config_data.get(CONF_VERIFY_SSL),
        config_data.get(CONF_TIMEOUT_ERROR_RETRIES),
        config_data.get(CONF_TIMEOUT_SECONDS),
    )


async def async_create_config_data(hass: HomeAssistant, config_entry: ConfigEntry):
    consider_home_seconds = config_entry.data.get(
        CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME
    )
    scan_interval_seconds = config_entry.data.get(
        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
    )
    update_interval = timedelta(seconds=scan_interval_seconds)

    # Load tracked entities from registry
    existing_entries = entity_registry.async_entries_for_config_entry(
        entity_registry.async_get(hass),
        config_entry.entry_id,
    )
    deco_data = TpLinkDecoData()
    client_data = {}

    # Populate client list with existing entries so that we keep track of disconnected clients
    # since deco list_clients only returns connected clients.
    last_states = restore_state.async_get(hass).last_states
    for entry in existing_entries:
        if entry.domain != DEVICE_TRACKER_DOMAIN:
            continue
        state = last_states.get(entry.entity_id)
        if state is None:
            continue
        device_type = state.state.attributes.get(ATTR_DEVICE_TYPE)
        if device_type is None:
            continue
        if device_type == DEVICE_TYPE_DECO:
            deco = TpLinkDeco(entry.unique_id)
            deco.name = entry.original_name
            deco_data.decos[entry.unique_id] = deco
        else:
            client = TpLinkDecoClient(entry.unique_id)
            client.name = entry.original_name
            client_data[entry.unique_id] = client

    return await async_create_and_refresh_coordinators(
        hass,
        config_entry.data,
        config_entry,
        consider_home_seconds,
        update_interval,
        deco_data,
        client_data,
    )


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Set up this integration using UI."""
    _LOGGER.debug("async_setup_entry: Config entry %s", config_entry.entry_id)

    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})

    data = await async_create_config_data(hass, config_entry)
    hass.data[DOMAIN][config_entry.entry_id] = data

    # Must be awaited (not wrapped in a task): otherwise unload can race
    # platform setup, and modern Home Assistant requires setup to be complete
    # before async_setup_entry returns.
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    _async_register_services(hass)

    config_entry.async_on_unload(config_entry.add_update_listener(update_listener))

    return True


def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services once for all config entries."""
    if hass.services.has_service(DOMAIN, SERVICE_REBOOT_DECO):
        return

    def _iter_deco_coordinators():
        for entry_data in hass.data.get(DOMAIN, {}).values():
            coordinator = entry_data.get(COORDINATOR_DECOS_KEY)
            if coordinator is not None:
                yield coordinator

    async def async_reboot_deco(service: ServiceCall) -> None:
        dr = device_registry.async_get(hass=hass)
        device_ids = cast(list[str], service.data.get(ATTR_DEVICE_ID))
        macs = []
        for device_id in device_ids:
            device = dr.async_get(device_id)
            if device is None:
                raise HomeAssistantError(
                    f"Device ID {device_id} is not a TP-Link Deco device"
                )
            mac = next(
                (
                    identifier[1]
                    for identifier in device.identifiers
                    if identifier[0] == DOMAIN
                ),
                None,
            )
            if mac is None:
                raise HomeAssistantError(
                    f"Device ID {device_id} does not have a {DOMAIN} MAC identifier"
                )
            macs.append(mac)

        # Route each MAC to the config entry that owns it (multi-entry safe).
        remaining = set(macs)
        for coordinator in _iter_deco_coordinators():
            entry_macs = [mac for mac in remaining if mac in coordinator.data.decos]
            if entry_macs:
                await coordinator.api.async_reboot_decos(entry_macs)
                remaining.difference_update(entry_macs)
        if remaining:
            raise HomeAssistantError(
                f"No loaded TP-Link Deco entry owns these devices: {sorted(remaining)}"
            )

    async def handle_pause_polling(service: ServiceCall) -> None:
        """Handle pause polling service."""
        for coordinator in _iter_deco_coordinators():
            if not coordinator.paused:
                coordinator.paused = True
                _LOGGER.info("TP-Link Deco polling paused")

    async def handle_resume_polling(service: ServiceCall) -> None:
        """Handle resume polling service."""
        for coordinator in _iter_deco_coordinators():
            if coordinator.paused:
                coordinator.paused = False
                _LOGGER.info("TP-Link Deco polling resumed")
                await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_REBOOT_DECO,
        async_reboot_deco,
        schema=vol.Schema(
            {
                vol.Required(ATTR_DEVICE_ID): vol.All(cv.ensure_list(str), [str]),
            }
        ),
    )
    hass.services.async_register(DOMAIN, SERVICE_PAUSE_POLLING, handle_pause_polling)
    hass.services.async_register(DOMAIN, SERVICE_RESUME_POLLING, handle_resume_polling)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    _LOGGER.debug("async_unload_entry: Config entry %s", config_entry.entry_id)

    domain_data = hass.data.get(DOMAIN, {})
    data = domain_data.get(config_entry.entry_id)

    if data is None:
        _LOGGER.debug(
            "async_unload_entry: No stored data for config entry %s",
            config_entry.entry_id,
        )
        return True

    # Unload the platforms first so no entity can trigger a refresh (and a
    # re-login) while/after we log out of the Deco.
    unloaded = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)

    if unloaded:
        deco_coordinator = data.get(COORDINATOR_DECOS_KEY)
        clients_coordinator = data.get(COORDINATOR_CLIENTS_KEY)

        if deco_coordinator is not None:
            await deco_coordinator.async_close()
        if clients_coordinator is not None:
            await clients_coordinator.async_close()

        # Logout from the Deco to free the admin session
        if deco_coordinator is not None:
            await deco_coordinator.api.async_logout()

        hass.data[DOMAIN].pop(config_entry.entry_id, None)
        if not hass.data[DOMAIN]:
            # Only remove the services when the last entry is unloaded.
            hass.services.async_remove(DOMAIN, SERVICE_REBOOT_DECO)
            hass.services.async_remove(DOMAIN, SERVICE_PAUSE_POLLING)
            hass.services.async_remove(DOMAIN, SERVICE_RESUME_POLLING)

    return unloaded


async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Update options."""
    _LOGGER.debug("update_listener: Reloading %s", config_entry.entry_id)
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_migrate_entry(hass, config_entry: ConfigEntry):
    """Migrate old entry."""
    _LOGGER.debug("Migrating from version %s", config_entry.version)

    version = config_entry.version
    new = {**config_entry.data}

    if version == 1:
        new[CONF_VERIFY_SSL] = True
        version = 2

    if version == 2:
        new[CONF_TIMEOUT_ERROR_RETRIES] = DEFAULT_TIMEOUT_ERROR_RETRIES
        version = 3

    if version == 3:
        new[CONF_TIMEOUT_SECONDS] = DEFAULT_TIMEOUT_SECONDS
        version = 4

    if version == 4:
        new[CONF_CLIENT_PREFIX] = ""
        new[CONF_CLIENT_POSTFIX] = ""
        new[CONF_DECO_PREFIX] = ""
        new[CONF_DECO_POSTFIX] = DEFAULT_DECO_POSTFIX
        version = 5

    if version == 5:
        new[CONF_HOST] = f"http://{new[CONF_HOST]}"
        version = 6

    if version != config_entry.version:
        # ConfigEntry attributes are read-only in recent Home Assistant:
        # the version must be updated through async_update_entry.
        hass.config_entries.async_update_entry(config_entry, data=new, version=version)
        _LOGGER.info("Migration to version %s successful", version)

    return True
