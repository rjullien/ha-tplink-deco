"""Adds config flow for TP-Link Deco."""

import logging
from typing import Any

import aiohttp
from homeassistant import config_entries
from homeassistant.components.device_tracker.const import CONF_CONSIDER_HOME
from homeassistant.components.device_tracker.const import CONF_SCAN_INTERVAL
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.const import CONF_PASSWORD
from homeassistant.const import CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
import voluptuous as vol

from .__init__ import create_api
from .const import CONF_CLIENT_POSTFIX
from .const import CONF_CLIENT_PREFIX
from .const import CONF_DECO_POSTFIX
from .const import CONF_DECO_PREFIX
from .const import CONF_TIMEOUT_ERROR_RETRIES
from .const import CONF_TIMEOUT_SECONDS
from .const import CONF_VERIFY_SSL
from .const import DEFAULT_CONSIDER_HOME
from .const import DEFAULT_DECO_POSTFIX
from .const import DEFAULT_SCAN_INTERVAL
from .const import DEFAULT_TIMEOUT_ERROR_RETRIES
from .const import DEFAULT_TIMEOUT_SECONDS
from .const import DOMAIN
from .exceptions import LoginForbiddenException
from .exceptions import LoginInvalidException
from .exceptions import TimeoutException

_LOGGER: logging.Logger = logging.getLogger(__name__)

SCAN_INTERVAL_OPTIONS = [10, 30, 60, 120, 180, 240, 300]


def _get_auth_schema(data: dict[str, Any]):
    if data is None:
        data = {}
    return {
        vol.Required(CONF_USERNAME, default=data.get(CONF_USERNAME, "admin")): str,
        vol.Required(CONF_PASSWORD, default=data.get(CONF_PASSWORD, "")): str,
    }


def _get_schema(data: dict[str, Any]):
    if data is None:
        data = {}
    schema = _get_auth_schema(data)
    scan_interval = data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    # Keep in sync with select.POLLING_INTERVAL_OPTIONS so an interval picked
    # via the select entity is not silently reset when reopening the form.
    if scan_interval not in SCAN_INTERVAL_OPTIONS:
        scan_interval = DEFAULT_SCAN_INTERVAL

    schema.update(
        {
            vol.Required(
                CONF_HOST, default=data.get(CONF_HOST, "http://192.168.0.1")
            ): str,
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=scan_interval,
            ): vol.In(SCAN_INTERVAL_OPTIONS),
            vol.Required(
                CONF_CONSIDER_HOME,
                default=data.get(CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME),
            ): vol.All(vol.Coerce(int), vol.Range(min=0)),
            vol.Required(
                CONF_TIMEOUT_ERROR_RETRIES,
                default=data.get(
                    CONF_TIMEOUT_ERROR_RETRIES, DEFAULT_TIMEOUT_ERROR_RETRIES
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=0)),
            vol.Required(
                CONF_TIMEOUT_SECONDS,
                default=data.get(CONF_TIMEOUT_SECONDS, DEFAULT_TIMEOUT_SECONDS),
            ): vol.All(vol.Coerce(int), vol.Range(min=5)),
            vol.Required(
                CONF_VERIFY_SSL,
                default=data.get(CONF_VERIFY_SSL, True),
            ): bool,
            vol.Optional(
                CONF_CLIENT_PREFIX,
                description={"suggested_value": data.get(CONF_CLIENT_PREFIX, "")},
            ): str,
            vol.Optional(
                CONF_CLIENT_POSTFIX,
                description={"suggested_value": data.get(CONF_CLIENT_POSTFIX, "")},
            ): str,
            vol.Optional(
                CONF_DECO_PREFIX,
                description={"suggested_value": data.get(CONF_DECO_PREFIX, "")},
            ): str,
            vol.Optional(
                CONF_DECO_POSTFIX,
                description={
                    "suggested_value": data.get(CONF_DECO_POSTFIX, DEFAULT_DECO_POSTFIX)
                },
            ): str,
        }
    )
    return schema


# We need to make sure the optional keys are set so that they get updated in update_listener async_update_entry() call
def _ensure_user_input_optionals(data: dict[str, Any]) -> None:
    for key in [
        CONF_CLIENT_PREFIX,
        CONF_CLIENT_POSTFIX,
        CONF_DECO_PREFIX,
        CONF_DECO_POSTFIX,
    ]:
        if key not in data:
            data[key] = ""


async def _async_test_credentials(hass: HomeAssistant, data: dict[str, Any]):
    """Return a dict of form errors, empty if the credentials are valid."""
    api = create_api(hass, data)
    try:
        # Exercise both endpoints the integration polls.
        await api.async_list_devices()
        await api.async_list_clients()
        return {}
    except TimeoutException:
        return {"base": "timeout_connect"}
    except (LoginForbiddenException, LoginInvalidException) as err:
        _LOGGER.error("Error authenticating credentials: %s", err)
        return {"base": "invalid_auth"}
    except aiohttp.ClientError as err:
        _LOGGER.error("Error connecting to host: %s", err)
        return {"base": "invalid_host"}
    except Exception as err:
        _LOGGER.exception("Error testing credentials: %s", err)
        return {"base": "unknown"}
    finally:
        # Release the test admin session so it does not pile up in the
        # Deco's limited session table.
        await api.async_logout()


class TplinkDecoFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for tplink_deco."""

    VERSION = 6
    reauth_entry: ConfigEntry = None

    def __init__(self):
        """Initialize."""
        self._errors = {}

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        self._errors = {}

        if user_input is not None:
            self._errors = await _async_test_credentials(self.hass, user_input)
            if len(self._errors) == 0:
                _ensure_user_input_optionals(user_input)
                return self.async_create_entry(
                    title=user_input[CONF_HOST], data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(_get_schema(user_input)),
            errors=self._errors,
        )

    async def async_step_reauth(self, user_input=None):
        """Perform reauth upon an API authentication error."""
        self.reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Dialog that informs the user that reauth is required."""
        self._errors = {}

        if user_input is not None:
            _ensure_user_input_optionals(user_input)
            data = dict(self.reauth_entry.data)
            data.update(user_input)

            self._errors = await _async_test_credentials(self.hass, data)
            if len(self._errors) == 0:
                self.hass.config_entries.async_update_entry(
                    self.reauth_entry, data=data
                )
                await self.hass.config_entries.async_reload(self.reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(_get_auth_schema(self.reauth_entry.data)),
            errors=self._errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        return TplinkDecoOptionsFlowHandler(config_entry)


class TplinkDecoOptionsFlowHandler(config_entries.OptionsFlow):
    """Config flow options handler for tplink_deco."""

    def __init__(self, config_entry: ConfigEntry):
        """Initialize tplink_deco options flow."""
        self._entry = config_entry
        self.data = dict(config_entry.data)
        self._errors = {}

    async def async_step_init(self, user_input: dict[str, Any] = None):
        """Handle a flow initialized by the user."""
        self._errors = {}

        if user_input is not None:
            _ensure_user_input_optionals(user_input)
            self.data.update(user_input)

            self._errors = await _async_test_credentials(self.hass, self.data)
            if len(self._errors) == 0:
                self.hass.config_entries.async_update_entry(
                    entry=self._entry,
                    title=self.data[CONF_HOST],
                    data=self.data,
                    options={},
                )
                return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(_get_schema(self.data)),
            errors=self._errors,
        )
