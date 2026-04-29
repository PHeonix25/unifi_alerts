"""Constants for the UniFi Alerts integration."""

from __future__ import annotations

DOMAIN = "unifi_alerts"

# ──────────────────────────────────────────────
# Config entry keys
# ──────────────────────────────────────────────
CONF_CONTROLLER_URL = "controller_url"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_API_KEY = "api_key"
CONF_AUTH_METHOD = "auth_method"
CONF_POLL_INTERVAL = "poll_interval"
CONF_CLEAR_TIMEOUT = "clear_timeout"
CONF_ENABLED_CATEGORIES = "enabled_categories"
CONF_VERIFY_SSL = "verify_ssl"
CONF_WEBHOOK_SECRET = "webhook_secret"
CONF_WEBHOOK_ID_SUFFIX = "webhook_id_suffix"
CONF_REGENERATE_WEBHOOK_SECRET = "regenerate_webhook_secret"
CONF_SITE = "site"
CONF_IS_UNIFI_OS = "is_unifi_os"

AUTH_METHOD_USERPASS = "userpass"
AUTH_METHOD_APIKEY = "apikey"

DEFAULT_POLL_INTERVAL = 60  # seconds
DEFAULT_CLEAR_TIMEOUT = 30  # minutes
DEFAULT_VERIFY_SSL = True  # disable in config flow if controller has a self-signed cert
DEFAULT_SITE = "default"
WEBHOOK_MAX_BODY_BYTES = 8192  # 8 KB ceiling on inbound webhook bodies
WEBHOOK_DEDUP_WINDOW_SECONDS = (
    5.0  # suppress duplicate (category, alert_key) pushes within this window
)

# ──────────────────────────────────────────────
# Category identifiers
# ──────────────────────────────────────────────
CATEGORY_NETWORK_DEVICE = "network_device"
CATEGORY_NETWORK_WAN = "network_wan"
CATEGORY_NETWORK_CLIENT = "network_client"
CATEGORY_SECURITY_THREAT = "security_threat"
CATEGORY_SECURITY_HONEYPOT = "security_honeypot"
CATEGORY_SECURITY_FIREWALL = "security_firewall"
CATEGORY_POWER = "power"

ALL_CATEGORIES: list[str] = [
    CATEGORY_NETWORK_DEVICE,
    CATEGORY_NETWORK_WAN,
    CATEGORY_NETWORK_CLIENT,
    CATEGORY_SECURITY_THREAT,
    CATEGORY_SECURITY_HONEYPOT,
    CATEGORY_SECURITY_FIREWALL,
    CATEGORY_POWER,
]

CATEGORY_LABELS: dict[str, str] = {
    CATEGORY_NETWORK_DEVICE: "Network: Device offline/online",
    CATEGORY_NETWORK_WAN: "Network: WAN offline/latency",
    CATEGORY_NETWORK_CLIENT: "Network: Client connect/disconnect",
    CATEGORY_SECURITY_THREAT: "Security: Threat / IDS detected",
    CATEGORY_SECURITY_HONEYPOT: "Security: Honeypot triggered",
    CATEGORY_SECURITY_FIREWALL: "Security: Firewall block",
    CATEGORY_POWER: "Power: PoE / power loss",
}

CATEGORY_ICONS: dict[str, str] = {
    CATEGORY_NETWORK_DEVICE: "mdi:lan-disconnect",
    CATEGORY_NETWORK_WAN: "mdi:wan",
    CATEGORY_NETWORK_CLIENT: "mdi:account-network",
    CATEGORY_SECURITY_THREAT: "mdi:shield-bug",
    CATEGORY_SECURITY_HONEYPOT: "mdi:bee",
    CATEGORY_SECURITY_FIREWALL: "mdi:firewall",
    CATEGORY_POWER: "mdi:lightning-bolt",
}

CATEGORY_ICONS_OK: dict[str, str] = {
    CATEGORY_NETWORK_DEVICE: "mdi:lan-check",
    CATEGORY_NETWORK_WAN: "mdi:web-check",
    CATEGORY_NETWORK_CLIENT: "mdi:account-check",
    CATEGORY_SECURITY_THREAT: "mdi:shield-check",
    CATEGORY_SECURITY_HONEYPOT: "mdi:shield-check",
    CATEGORY_SECURITY_FIREWALL: "mdi:shield-check",
    CATEGORY_POWER: "mdi:power-plug",
}

# ──────────────────────────────────────────────
# UniFi event key → category mapping
# Keys are prefixes/substrings from the 'key' field in UniFi alarm payloads.
# Sourced from community reverse-engineering of the UniFi controller API.
# ──────────────────────────────────────────────
UNIFI_KEY_TO_CATEGORY: dict[str, str] = {
    # Network: device offline/online — Access Points
    "EVT_AP_Disconnected": CATEGORY_NETWORK_DEVICE,
    "EVT_AP_Connected": CATEGORY_NETWORK_DEVICE,
    "EVT_AP_Lost_Contact": CATEGORY_NETWORK_DEVICE,
    "EVT_AP_Adopted": CATEGORY_NETWORK_DEVICE,
    "EVT_AP_AutoReadopted": CATEGORY_NETWORK_DEVICE,
    "EVT_AP_Restarted": CATEGORY_NETWORK_DEVICE,  # also matches EVT_AP_RestartedUnknown
    "EVT_AP_Upgraded": CATEGORY_NETWORK_DEVICE,
    "EVT_AP_UpgradeFailed": CATEGORY_NETWORK_DEVICE,
    "EVT_AP_UpgradeScheduled": CATEGORY_NETWORK_DEVICE,
    "EVT_AP_Isolated": CATEGORY_NETWORK_DEVICE,
    "EVT_AP_Deleted": CATEGORY_NETWORK_DEVICE,
    # Network: device offline/online — Switches
    "EVT_SW_Disconnected": CATEGORY_NETWORK_DEVICE,
    "EVT_SW_Connected": CATEGORY_NETWORK_DEVICE,
    "EVT_SW_Lost_Contact": CATEGORY_NETWORK_DEVICE,
    "EVT_SW_Adopted": CATEGORY_NETWORK_DEVICE,
    "EVT_SW_AutoReadopted": CATEGORY_NETWORK_DEVICE,
    "EVT_SW_Restarted": CATEGORY_NETWORK_DEVICE,  # also matches EVT_SW_RestartedUnknown
    "EVT_SW_Upgraded": CATEGORY_NETWORK_DEVICE,
    "EVT_SW_Deleted": CATEGORY_NETWORK_DEVICE,
    "EVT_SW_StpPortBlocking": CATEGORY_NETWORK_DEVICE,
    # Network: device offline/online — Gateways
    "EVT_GW_Disconnected": CATEGORY_NETWORK_DEVICE,
    "EVT_GW_Connected": CATEGORY_NETWORK_DEVICE,
    "EVT_GW_Lost_Contact": CATEGORY_NETWORK_DEVICE,
    "EVT_GW_Adopted": CATEGORY_NETWORK_DEVICE,
    "EVT_GW_AutoReadopted": CATEGORY_NETWORK_DEVICE,
    "EVT_GW_Restarted": CATEGORY_NETWORK_DEVICE,  # also matches EVT_GW_RestartedUnknown
    "EVT_GW_Upgraded": CATEGORY_NETWORK_DEVICE,
    "EVT_GW_Deleted": CATEGORY_NETWORK_DEVICE,
    # Network: device offline/online — Dream Machine (DM prefix)
    "EVT_DM_Connected": CATEGORY_NETWORK_DEVICE,
    "EVT_DM_Lost_Contact": CATEGORY_NETWORK_DEVICE,
    "EVT_DM_Upgraded": CATEGORY_NETWORK_DEVICE,
    # Network: device offline/online — Smart power / outlet devices (XG prefix)
    "EVT_XG_AutoReadopted": CATEGORY_NETWORK_DEVICE,
    "EVT_XG_Connected": CATEGORY_NETWORK_DEVICE,
    "EVT_XG_Lost_Contact": CATEGORY_NETWORK_DEVICE,
    # Network: device offline/online — IPS sensor
    "EVT_IPS_IDS_Disconnected": CATEGORY_NETWORK_DEVICE,
    # Network: WAN
    "EVT_GW_WANTransition": CATEGORY_NETWORK_WAN,
    "EVT_GW_Failover": CATEGORY_NETWORK_WAN,
    "EVT_GW_WAN_Transition": CATEGORY_NETWORK_WAN,
    "EVT_GW_Internet_Access": CATEGORY_NETWORK_WAN,
    # Network: client — wireless users
    "EVT_WU_Connected": CATEGORY_NETWORK_CLIENT,
    "EVT_WU_Disconnected": CATEGORY_NETWORK_CLIENT,
    "EVT_WU_Roam": CATEGORY_NETWORK_CLIENT,  # also matches EVT_WU_RoamRadio
    # Network: client — wireless guests
    "EVT_WG_Connected": CATEGORY_NETWORK_CLIENT,
    "EVT_WG_Disconnected": CATEGORY_NETWORK_CLIENT,
    "EVT_WG_Roam": CATEGORY_NETWORK_CLIENT,  # also matches EVT_WG_RoamRadio
    "EVT_WG_AuthorizationEnded": CATEGORY_NETWORK_CLIENT,
    # Network: client — wired users
    "EVT_LU_Connected": CATEGORY_NETWORK_CLIENT,
    "EVT_LU_Disconnected": CATEGORY_NETWORK_CLIENT,
    # Network: client — LAN guests
    "EVT_LG_Connected": CATEGORY_NETWORK_CLIENT,
    "EVT_LG_Disconnected": CATEGORY_NETWORK_CLIENT,
    # Security: threat / IDS
    "EVT_IPS_ThreatDetected": CATEGORY_SECURITY_THREAT,
    "EVT_IPS_IpsAlert": CATEGORY_SECURITY_THREAT,
    "EVT_IDS_Alert": CATEGORY_SECURITY_THREAT,
    "EVT_GW_ThreatDetected": CATEGORY_SECURITY_THREAT,
    "EVT_AP_DetectRogueAP": CATEGORY_SECURITY_THREAT,
    "EVT_AP_RadarDetected": CATEGORY_SECURITY_THREAT,  # DFS radar detection
    "EVT_SW_DetectRogueDHCP": CATEGORY_SECURITY_THREAT,
    # Security: honeypot
    "EVT_GW_Honeypot": CATEGORY_SECURITY_HONEYPOT,
    "EVT_GW_HoneypotDetected": CATEGORY_SECURITY_HONEYPOT,
    # Security: firewall
    "EVT_GW_GeoIPFilteredTraffic": CATEGORY_SECURITY_FIREWALL,
    "EVT_GW_TrafficRoute": CATEGORY_SECURITY_FIREWALL,
    "EVT_GW_BlockedTraffic": CATEGORY_SECURITY_FIREWALL,
    "EVT_LC_Blocked": CATEGORY_SECURITY_FIREWALL,  # wired client blocked by admin
    "EVT_WC_Blocked": CATEGORY_SECURITY_FIREWALL,  # wireless client blocked by admin
    # Power
    "EVT_SW_PoEDisconnect": CATEGORY_POWER,
    "EVT_SW_PoeDisconnect": CATEGORY_POWER,  # alt. casing seen on some firmware
    "EVT_SW_PoeOverload": CATEGORY_POWER,
    "EVT_SW_Overheat": CATEGORY_POWER,
    "EVT_AP_PowerCycled": CATEGORY_POWER,
    "EVT_GW_PowerLoss": CATEGORY_POWER,
    "EVT_XG_OutletPowerCycle": CATEGORY_POWER,
    "EVT_USP_RpsPowerDeniedByPsuOverload": CATEGORY_POWER,
    "EVT_UPS_": CATEGORY_POWER,
}

# Webhook IDs — one per category, auto-registered by the integration.
# The optional `suffix` (CONF_WEBHOOK_ID_SUFFIX, generated per-entry by the
# config flow) prevents two config entries from colliding on the same webhook
# ID. Entries created before the suffix was introduced pass `suffix=""` and
# fall back to the legacy format so their existing UniFi Alarm Manager URLs
# keep working — only multi-entry users need to re-paste URLs after adding a
# second entry, which they had to do anyway because that case was silently
# broken pre-fix.
WEBHOOK_ID_PREFIX = "unifi_alerts_"


def webhook_id_for_category(category: str, suffix: str = "") -> str:
    if suffix:
        return f"{WEBHOOK_ID_PREFIX}{suffix}_{category}"
    return f"{WEBHOOK_ID_PREFIX}{category}"


# Runtime data keys (stored in hass.data[DOMAIN][entry_id])
DATA_COORDINATOR = "coordinator"
DATA_WEBHOOK_IDS = "webhook_ids"
DATA_UNREGISTER_WEBHOOKS = "unregister_webhooks"
