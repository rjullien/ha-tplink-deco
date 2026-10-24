"""Constants for TP-Link Deco."""

from homeassistant.components.device_tracker.const import (
    DEFAULT_CONSIDER_HOME as DEFAULT_CONSIDER_HOME_SPAN,
)

# Base component constants
DOMAIN = "tplink_deco"

COORDINATOR_CLIENTS_KEY = "clients"
COORDINATOR_DECOS_KEY = "decos"

DEFAULT_CONSIDER_HOME = DEFAULT_CONSIDER_HOME_SPAN.total_seconds()
DEFAULT_DECO_POSTFIX = "Deco"
DEFAULT_LINK_CLIENT_DEVICES = True
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_TIMEOUT_ERROR_RETRIES = 1
DEFAULT_TIMEOUT_SECONDS = 30

DEVICE_TYPE_CLIENT = "client"
DEVICE_TYPE_DECO = "deco"

# Attributes
ATTR_BSSID_BAND2_4 = "bssid_band2_4"
ATTR_BSSID_BAND5 = "bssid_band5"
ATTR_BACKHAUL_BSSID_BAND2_4 = "backhaul_bssid_band2_4"
ATTR_BACKHAUL_BSSID_BAND5 = "backhaul_bssid_band5"
ATTR_CLIENT_MESH = "client_mesh"
ATTR_CLIENT_TYPE = "client_type"
ATTR_CONNECTION_TYPE = "connection_type"
ATTR_DECO_DEVICE = "deco_device"
ATTR_DECO_MAC = "deco_mac"
ATTR_DEVICE_ID = "device_id"
ATTR_DEVICE_MODEL = "device_model"
ATTR_DEVICE_TYPE = "device_type"
ATTR_DOWN_KILOBYTES_PER_S = "down_kilobytes_per_s"
ATTR_EASYMESH_ROLE = "easymesh_role"
ATTR_INTERFACE = "interface"
ATTR_INTERNET_STATUS_MESSAGE = "internet_status_message"
ATTR_INTERNET_ONLINE = "internet_online"
ATTR_MASTER = "master"
ATTR_PARENT_DEVICE_ID = "parent_device_id"
ATTR_PARENT_MAC = "parent_mac"
ATTR_RX_RATE_BAND2_4 = "rx_rate_band2_4"
ATTR_RX_RATE_BAND5 = "rx_rate_band5"
ATTR_SIGNAL_BAND2_4 = "signal_band2_4"
ATTR_SIGNAL_BAND5 = "signal_band5"
ATTR_SIGNAL_BAND6 = "signal_band6"
ATTR_SIGNAL_STRENGTH_BAND2_4 = "signal_strength_band2_4"
ATTR_SIGNAL_STRENGTH_BAND5 = "signal_strength_band5"
ATTR_SIGNAL_STRENGTH_BAND6 = "signal_strength_band6"
ATTR_TX_RATE_BAND2_4 = "tx_rate_band2_4"
ATTR_TX_RATE_BAND5 = "tx_rate_band5"
ATTR_UP_KILOBYTES_PER_S = "up_kilobytes_per_s"
ATTR_UI_DEVICE_NAME = "ui_device_name"
ATTR_WIRED_PORTS = "wired_ports"
ATTR_WIRED_PORT_SPEED_MIN = "wired_port_speed_min"
ATTR_WIRE_TYPE = "wire_type"

# Config
CONF_CLIENT_PREFIX = "client_prefix"
CONF_CLIENT_POSTFIX = "client_postfix"
CONF_DECO_PREFIX = "deco_prefix"
CONF_DECO_POSTFIX = "deco_postfix"
CONF_LINK_CLIENT_DEVICES = "link_client_devices"
CONF_TIMEOUT_ERROR_RETRIES = "timeout_error_retries"
CONF_TIMEOUT_SECONDS = "timeout_seconds"
CONF_VERIFY_SSL = "verify_ssl"

# Signals
SIGNAL_CLIENT_ADDED = f"{DOMAIN}-client-added"
SIGNAL_DECO_ADDED = f"{DOMAIN}-deco-added"

# Services
SERVICE_REBOOT_DECO = "reboot_deco"
SERVICE_PAUSE_POLLING = "pause_polling"
SERVICE_RESUME_POLLING = "resume_polling"
# Platforms
PLATFORMS = ["device_tracker", "sensor", "binary_sensor", "switch", "select"]
