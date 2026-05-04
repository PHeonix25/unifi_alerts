"""Data models for UniFi Alerts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .coordinator import UniFiAlertsCoordinator
    from .unifi_client import UniFiClient


@dataclass
class UniFiAlert:
    """Represents a single alert received from UniFi (via webhook or poll)."""

    category: str
    message: str
    received_at: datetime
    raw: dict = field(default_factory=dict)

    # Optional enrichment fields parsed from the UniFi payload
    key: str = ""
    device_name: str = ""
    site: str = ""
    severity: str = ""

    @classmethod
    def from_webhook_payload(cls, category: str, payload: dict) -> UniFiAlert:
        """Build an alert from a raw UniFi Alarm Manager webhook POST body."""
        message = (
            payload.get("message")
            or payload.get("msg")
            or payload.get("text")
            or payload.get("description")
            or "Unknown alert"
        )
        return cls(
            category=category,
            message=str(message)[:255],
            received_at=datetime.now(UTC),
            raw=payload,
            key=payload.get("key", ""),
            device_name=payload.get("device_name")
            or payload.get("ap_name")
            or payload.get("sw_name")
            or "",
            site=payload.get("site_name") or payload.get("site") or "",
            severity=payload.get("severity") or payload.get("subsystem") or "",
        )

    @classmethod
    def from_api_alarm(cls, category: str, alarm: dict) -> UniFiAlert:
        """Build an alert from a polled UniFi controller alarm record."""
        message = alarm.get("msg") or alarm.get("message") or alarm.get("key") or "Unknown alert"
        # UniFi stores timestamps as epoch milliseconds in some fields
        ts = alarm.get("datetime") or alarm.get("timestamp")
        try:
            received_at = datetime.fromisoformat(str(ts)) if ts else datetime.now(UTC)
        except (ValueError, TypeError):
            received_at = datetime.now(UTC)

        return cls(
            category=category,
            message=str(message)[:255],
            received_at=received_at,
            raw=alarm,
            key=alarm.get("key", ""),
            device_name=alarm.get("device_name") or alarm.get("ap_name") or "",
            site=alarm.get("site_name") or "",
            severity=alarm.get("severity") or alarm.get("subsystem") or "",
        )


@dataclass
class CategoryState:
    """Runtime state for a single alert category."""

    category: str
    enabled: bool = True
    is_alerting: bool = False
    last_alert: UniFiAlert | None = None
    alert_count: int = 0  # incremented by webhooks
    open_count: int = 0  # set by polling (unarchived alarms)
    last_cleared_at: datetime | None = None

    def apply_alert(self, alert: UniFiAlert) -> None:
        self.is_alerting = True
        self.last_alert = alert
        self.alert_count += 1

    def clear(self) -> None:
        self.is_alerting = False
        self.last_cleared_at = datetime.now(UTC)


@dataclass
class RuntimeData:
    """Data stored on the config entry as ``entry.runtime_data``."""

    coordinator: UniFiAlertsCoordinator
    webhook_urls: dict[str, str]
    unregister_webhooks: Callable[[], None]
    client: UniFiClient
