"""Button entities for TP-Link Deco."""

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import COORDINATOR_DECOS_KEY
from .const import DOMAIN
from .coordinator import TplinkDecoUpdateCoordinator
from .device import create_device_info

_LOGGER: logging.Logger = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button platform."""
    coordinator: TplinkDecoUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ][COORDINATOR_DECOS_KEY]
    async_add_entities([DecoRefreshTopologyButton(coordinator)])


class DecoRefreshTopologyButton(ButtonEntity):
    """Button that manually triggers a device-topology refresh.

    Pressing this button calls async_list_devices on the API, updates the deco
    coordinator data, and propagates the result to all subscribed entities.
    Useful after adding or removing a Deco node from the mesh without waiting
    for the 12-hour automatic topology refresh.
    """

    _attr_has_entity_name = True
    _attr_name = "Refresh topology"
    _attr_icon = "mdi:refresh-circle"
    _attr_unique_id = "tplink_deco_refresh_topology"

    def __init__(self, coordinator: TplinkDecoUpdateCoordinator) -> None:
        self._coordinator = coordinator

    @property
    def device_info(self) -> DeviceInfo | None:
        """Attach button to the master Deco device."""
        master_deco = self._coordinator.data.master_deco
        if master_deco is None:
            return None
        return create_device_info(master_deco, master_deco)

    async def async_press(self) -> None:
        """Handle button press: refresh device topology."""
        _LOGGER.info(
            "Refresh topology button pressed — fetching device list from Deco API"
        )
        await self._coordinator.async_refresh()
        deco_count = len(self._coordinator.data.decos)
        _LOGGER.info(
            "Topology refresh complete: %d deco node(s) in mesh", deco_count
        )
