"""Tests for the UniFi HTTP client."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CATEGORY_NETWORK_DEVICE,
    CATEGORY_NETWORK_WAN,
    CATEGORY_SECURITY_THREAT,
    CATEGORY_SECURITY_HONEYPOT,
    CATEGORY_SECURITY_FIREWALL,
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
        ("EVT_AP_Disconnected", CATEGORY_NETWORK_DEVICE),
        ("EVT_SW_Connected", CATEGORY_NETWORK_DEVICE),
        ("EVT_GW_Connected", CATEGORY_NETWORK_DEVICE),
        ("EVT_GW_WANTransition", CATEGORY_NETWORK_WAN),
        ("EVT_GW_Failover", CATEGORY_NETWORK_WAN),
        ("EVT_IPS_ThreatDetected", CATEGORY_SECURITY_THREAT),
        ("EVT_GW_Honeypot", CATEGORY_SECURITY_HONEYPOT),
        ("EVT_GW_BlockedTraffic", CATEGORY_SECURITY_FIREWALL),
        ("EVT_SW_PoEDisconnect", CATEGORY_POWER),
        ("EVT_GW_PowerLoss", CATEGORY_POWER),
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
