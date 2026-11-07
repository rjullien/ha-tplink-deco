"""Tests for optional mobile data usage support."""

import logging
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from custom_components.tplink_deco.api import TplinkDecoApi
from custom_components.tplink_deco.coordinator import TpLinkDeco
from custom_components.tplink_deco.coordinator import TpLinkDecoData
from custom_components.tplink_deco.exceptions import TimeoutException
from custom_components.tplink_deco.mobile import TplinkDecoMobileDataUpdateCoordinator
from custom_components.tplink_deco.mobile import supports_mobile_data
from custom_components.tplink_deco.sensor import TplinkMobileDataUsageSensor


def _api(response: dict) -> TplinkDecoApi:
    api = TplinkDecoApi(
        session=MagicMock(),
        host="http://192.168.1.1",
        username="admin",
        password="password",
        verify_ssl=False,
    )
    api.async_login_if_needed = AsyncMock()
    api._encode_payload = MagicMock(return_value="payload")
    api._async_post = AsyncMock(return_value={"data": "encrypted"})
    api._decrypt_data = MagicMock(return_value=response)
    api._check_authenticated_data_error_code = MagicMock()
    return api


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [217896125, "217896125"])
async def test_mobile_data_usage_parses_kib_value(value):
    api = _api({"result": {"mobile_cpe": {"data_usage": value}}})

    assert await api._async_get_mobile_data_usage() == 217896125
    api._async_post.assert_awaited_once_with(
        "Get Mobile Data Usage",
        "http://192.168.1.1/cgi-bin/luci/;stok=None/admin/network",
        params={"form": "internet"},
        data="payload",
    )
    api._check_authenticated_data_error_code.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        {},
        {"result": {}},
        {"result": {"mobile_cpe": {}}},
        {"result": {"mobile_cpe": {"data_usage": True}}},
        {"result": {"mobile_cpe": {"data_usage": -1}}},
        {"result": {"mobile_cpe": {"data_usage": "invalid"}}},
    ],
)
async def test_mobile_data_usage_ignores_unsupported_or_invalid_values(response):
    api = _api(response)

    assert await api._async_get_mobile_data_usage() is None


@pytest.mark.asyncio
async def test_mobile_data_coordinator_respects_polling_pause():
    coordinator = object.__new__(TplinkDecoMobileDataUpdateCoordinator)
    coordinator.api = MagicMock()
    coordinator.api.async_get_mobile_data_usage = AsyncMock(return_value=200)
    coordinator._deco_coordinator = MagicMock(paused=True)
    coordinator.data = 100

    assert await coordinator._async_update_data() == 100
    coordinator.api.async_get_mobile_data_usage.assert_not_awaited()


@pytest.mark.asyncio
async def test_mobile_data_coordinator_fetches_supported_model():
    coordinator = object.__new__(TplinkDecoMobileDataUpdateCoordinator)
    coordinator.api = MagicMock()
    coordinator.api.async_get_mobile_data_usage = AsyncMock(return_value=217896125)
    master_deco = TpLinkDeco("AA:BB:CC:DD:EE:01")
    master_deco.device_model = "Deco X50-5G"
    coordinator._deco_coordinator = MagicMock(
        paused=False,
        data=TpLinkDecoData(master_deco, {master_deco.mac: master_deco}),
    )

    assert await coordinator._async_update_data() == 217896125
    coordinator.api.async_get_mobile_data_usage.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["Deco X50", "XE75 Pro"])
async def test_mobile_data_coordinator_skips_non_mobile_model(model):
    coordinator = object.__new__(TplinkDecoMobileDataUpdateCoordinator)
    coordinator.api = MagicMock()
    coordinator.api.async_get_mobile_data_usage = AsyncMock(return_value=217896125)
    master_deco = TpLinkDeco("AA:BB:CC:DD:EE:01")
    master_deco.device_model = model
    coordinator._deco_coordinator = MagicMock(
        paused=False,
        data=TpLinkDecoData(master_deco, {master_deco.mac: master_deco}),
    )

    assert await coordinator._async_update_data() is None
    coordinator.api.async_get_mobile_data_usage.assert_not_awaited()


@pytest.mark.asyncio
async def test_mobile_failure_does_not_change_main_deco_state():
    api = _api({})
    api.async_get_mobile_data_usage = AsyncMock(
        side_effect=TimeoutException("mobile timeout")
    )
    api.clear_auth = MagicMock()
    master_deco = TpLinkDeco("AA:BB:CC:DD:EE:01")
    master_deco.device_model = "Deco X50-4G"
    main_data = TpLinkDecoData(master_deco, {master_deco.mac: master_deco})
    main_coordinator = MagicMock(
        paused=False,
        data=main_data,
        last_update_success=True,
    )
    coordinator = object.__new__(TplinkDecoMobileDataUpdateCoordinator)
    coordinator.api = api
    coordinator._deco_coordinator = main_coordinator
    coordinator.data = 217896125

    with pytest.raises(TimeoutException):
        await coordinator._async_update_data()

    assert coordinator.data == 217896125
    assert main_coordinator.data is main_data
    assert main_coordinator.last_update_success is True
    api.clear_auth.assert_not_called()


@pytest.mark.parametrize(
    "model,supported",
    [
        ("Deco X50-5G", True),
        ("X20-4G", True),
        ("X50", False),
        (None, False),
    ],
)
def test_mobile_data_model_detection(model, supported):
    assert supports_mobile_data(model) is supported


@pytest.mark.asyncio
async def test_async_get_mobile_data_usage_uses_configured_timeout_retries():
    api = _api({})
    api._timeout_error_retries = 1
    api._async_get_mobile_data_usage = AsyncMock(
        side_effect=[TimeoutException("Get Mobile Data Usage"), 200]
    )

    assert await api.async_get_mobile_data_usage() == 200
    assert api._async_get_mobile_data_usage.await_count == 2


@pytest.mark.asyncio
async def test_async_get_mobile_data_usage_does_not_log_internet_payload(
    api, mock_session, caplog
):
    secrets = ("private-network-name", "private-password", "private-psk")
    payload = {
        "error_code": 0,
        "result": {
            "mobile_cpe": {
                "data_usage": 200,
                "ssid": secrets[0],
                "password": secrets[1],
                "psk": secrets[2],
            }
        },
    }
    api._aes_key_bytes = b"0123456789abcdef"
    api._aes_iv_bytes = b"abcdef0123456789"
    api._stok = "token"
    api._cookie = "sysauth=abc"
    api._seq = 1
    api.async_login_if_needed = AsyncMock()
    api._encode_payload = MagicMock(return_value="request-payload")
    response = MagicMock()
    response.status = 200
    response.history = ()
    response.headers.getall.return_value = []
    response.json = AsyncMock(return_value={"data": api._encode_data(payload)})
    response.raise_for_status = MagicMock()
    mock_session.post.return_value = response

    caplog.set_level(logging.DEBUG, logger="custom_components.tplink_deco")

    assert await api.async_get_mobile_data_usage() == 200
    assert all(secret not in caplog.text for secret in secrets)


def test_mobile_data_usage_sensor_uses_master_deco():
    master_deco = TpLinkDeco("AA:BB:CC:DD:EE:01")
    master_deco.name = "Living Room"
    coordinator_decos = MagicMock()
    coordinator_decos.data = TpLinkDecoData(master_deco, {master_deco.mac: master_deco})
    coordinator_mobile = MagicMock()
    coordinator_mobile.data = 217896125

    sensor = TplinkMobileDataUsageSensor(
        coordinator_decos,
        coordinator_mobile,
        master_deco.mac,
    )

    assert sensor.native_value == 217896125
    assert sensor.unique_id == f"{master_deco.mac}_mobile_data_usage"
