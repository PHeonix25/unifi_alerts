"""Tests for the UniFi HTTP client."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CATEGORY_NETWORK_CLIENT,
    CATEGORY_NETWORK_DEVICE,
    CATEGORY_NETWORK_WAN,
    CATEGORY_SECURITY_FIREWALL,
    CATEGORY_SECURITY_HONEYPOT,
    CATEGORY_SECURITY_THREAT,
    CATEGORY_POWER,
)
from custom_components.unifi_alerts.unifi_client import UniFiClient


def make_client(config: dict | None = None) -> UniFiClient:
    session = MagicMock()
    cfg = config or {
        "username": "admin",
        "password": "password",
        "verify_ssl": False,
    }
    return UniFiClient(session, "https://192.168.1.1", cfg)


class TestClassify:
    """Test the static _classify method for event key → category mapping."""

    @pytest.mark.parametrize("key,expected", [
        # Access points
        ("EVT_AP_Disconnected", CATEGORY_NETWORK_DEVICE),
        ("EVT_AP_Connected", CATEGORY_NETWORK_DEVICE),
        ("EVT_AP_Lost_Contact", CATEGORY_NETWORK_DEVICE),
        ("EVT_AP_Adopted", CATEGORY_NETWORK_DEVICE),
        ("EVT_AP_AutoReadopted", CATEGORY_NETWORK_DEVICE),
        ("EVT_AP_Restarted", CATEGORY_NETWORK_DEVICE),
        ("EVT_AP_RestartedUnknown", CATEGORY_NETWORK_DEVICE),  # matched by EVT_AP_Restarted prefix
        ("EVT_AP_Upgraded", CATEGORY_NETWORK_DEVICE),
        ("EVT_AP_UpgradeFailed", CATEGORY_NETWORK_DEVICE),
        ("EVT_AP_UpgradeScheduled", CATEGORY_NETWORK_DEVICE),
        ("EVT_AP_Isolated", CATEGORY_NETWORK_DEVICE),
        ("EVT_AP_Deleted", CATEGORY_NETWORK_DEVICE),
        # Switches
        ("EVT_SW_Connected", CATEGORY_NETWORK_DEVICE),
        ("EVT_SW_Lost_Contact", CATEGORY_NETWORK_DEVICE),
        ("EVT_SW_Adopted", CATEGORY_NETWORK_DEVICE),
        ("EVT_SW_AutoReadopted", CATEGORY_NETWORK_DEVICE),
        ("EVT_SW_Restarted", CATEGORY_NETWORK_DEVICE),
        ("EVT_SW_RestartedUnknown", CATEGORY_NETWORK_DEVICE),  # matched by EVT_SW_Restarted prefix
        ("EVT_SW_Upgraded", CATEGORY_NETWORK_DEVICE),
        ("EVT_SW_StpPortBlocking", CATEGORY_NETWORK_DEVICE),
        # Gateways
        ("EVT_GW_Connected", CATEGORY_NETWORK_DEVICE),
        ("EVT_GW_Lost_Contact", CATEGORY_NETWORK_DEVICE),
        ("EVT_GW_Adopted", CATEGORY_NETWORK_DEVICE),
        ("EVT_GW_Restarted", CATEGORY_NETWORK_DEVICE),
        ("EVT_GW_RestartedUnknown", CATEGORY_NETWORK_DEVICE),  # matched by EVT_GW_Restarted prefix
        ("EVT_GW_Upgraded", CATEGORY_NETWORK_DEVICE),
        # Dream Machine
        ("EVT_DM_Connected", CATEGORY_NETWORK_DEVICE),
        ("EVT_DM_Lost_Contact", CATEGORY_NETWORK_DEVICE),
        ("EVT_DM_Upgraded", CATEGORY_NETWORK_DEVICE),
        # Smart power / outlet devices
        ("EVT_XG_AutoReadopted", CATEGORY_NETWORK_DEVICE),
        ("EVT_XG_Connected", CATEGORY_NETWORK_DEVICE),
        ("EVT_XG_Lost_Contact", CATEGORY_NETWORK_DEVICE),
        # WAN
        ("EVT_GW_WANTransition", CATEGORY_NETWORK_WAN),
        ("EVT_GW_Failover", CATEGORY_NETWORK_WAN),
        # Clients — wireless users
        ("EVT_WU_Connected", CATEGORY_NETWORK_CLIENT),
        ("EVT_WU_Disconnected", CATEGORY_NETWORK_CLIENT),
        ("EVT_WU_Roam", CATEGORY_NETWORK_CLIENT),
        ("EVT_WU_RoamRadio", CATEGORY_NETWORK_CLIENT),          # matched by EVT_WU_Roam prefix
        # Clients — wireless guests
        ("EVT_WG_Connected", CATEGORY_NETWORK_CLIENT),
        ("EVT_WG_Disconnected", CATEGORY_NETWORK_CLIENT),
        ("EVT_WG_Roam", CATEGORY_NETWORK_CLIENT),
        ("EVT_WG_RoamRadio", CATEGORY_NETWORK_CLIENT),          # matched by EVT_WG_Roam prefix
        ("EVT_WG_AuthorizationEnded", CATEGORY_NETWORK_CLIENT),
        # Clients — wired users / LAN guests
        ("EVT_LU_Connected", CATEGORY_NETWORK_CLIENT),
        ("EVT_LU_Disconnected", CATEGORY_NETWORK_CLIENT),
        ("EVT_LG_Connected", CATEGORY_NETWORK_CLIENT),
        ("EVT_LG_Disconnected", CATEGORY_NETWORK_CLIENT),
        # Security: threat
        ("EVT_IPS_ThreatDetected", CATEGORY_SECURITY_THREAT),
        ("EVT_IPS_IpsAlert", CATEGORY_SECURITY_THREAT),
        ("EVT_IDS_Alert", CATEGORY_SECURITY_THREAT),
        ("EVT_AP_DetectRogueAP", CATEGORY_SECURITY_THREAT),
        ("EVT_AP_RadarDetected", CATEGORY_SECURITY_THREAT),
        ("EVT_SW_DetectRogueDHCP", CATEGORY_SECURITY_THREAT),
        # Security: honeypot
        ("EVT_GW_Honeypot", CATEGORY_SECURITY_HONEYPOT),
        ("EVT_GW_HoneypotDetected", CATEGORY_SECURITY_HONEYPOT),
        # Security: firewall
        ("EVT_GW_BlockedTraffic", CATEGORY_SECURITY_FIREWALL),
        ("EVT_LC_Blocked", CATEGORY_SECURITY_FIREWALL),
        ("EVT_WC_Blocked", CATEGORY_SECURITY_FIREWALL),
        # Power
        ("EVT_SW_PoEDisconnect", CATEGORY_POWER),
        ("EVT_SW_PoeDisconnect", CATEGORY_POWER),
        ("EVT_SW_PoeOverload", CATEGORY_POWER),
        ("EVT_SW_Overheat", CATEGORY_POWER),
        ("EVT_AP_PowerCycled", CATEGORY_POWER),
        ("EVT_GW_PowerLoss", CATEGORY_POWER),
        ("EVT_XG_OutletPowerCycle", CATEGORY_POWER),
        ("EVT_USP_RpsPowerDeniedByPsuOverload", CATEGORY_POWER),
        ("EVT_UPS_LowBattery", CATEGORY_POWER),                 # matched by EVT_UPS_ prefix
    ])
    def test_known_keys(self, key: str, expected: str):
        alarm = {"key": key}
        result = UniFiClient._classify(alarm)
        assert result == expected, f"Key {key!r} should map to {expected}, got {result}"

    def test_unknown_key_returns_none(self):
        alarm = {"key": "EVT_UNKNOWN_THING"}
        assert UniFiClient._classify(alarm) is None

    def test_missing_key_returns_none(self):
        alarm = {}
        assert UniFiClient._classify(alarm) is None


class TestNetworkPath:
    def test_non_unifi_os_path_unchanged(self):
        client = make_client()
        client._is_unifi_os = False
        assert client._network_path("/api/s/default/alarm") == "/api/s/default/alarm"

    def test_unifi_os_adds_proxy_prefix(self):
        client = make_client()
        client._is_unifi_os = True
        assert client._network_path("/api/s/default/alarm") == "/proxy/network/api/s/default/alarm"


class TestHeaders:
    def test_userpass_auth_no_api_key_header(self):
        client = make_client()
        client._auth_method = "userpass"
        headers = client._headers()
        assert "X-API-Key" not in headers

    def test_apikey_auth_adds_header(self):
        client = make_client({"api_key": "test-key-123", "verify_ssl": False})
        client._auth_method = "apikey"
        headers = client._headers()
        assert headers.get("X-API-Key") == "test-key-123"
