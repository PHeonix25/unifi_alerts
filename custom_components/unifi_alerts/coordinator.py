"""DataUpdateCoordinator for UniFi Alerts."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ALL_CATEGORIES,
    CONF_CLEAR_TIMEOUT,
    CONF_ENABLED_CATEGORIES,
    CONF_POLL_INTERVAL,
    CONF_SITE,
    DEFAULT_CLEAR_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SITE,
    DOMAIN,
)
from .models import CategoryState, UniFiAlert
from .unifi_client import CannotConnectError, InvalidAuthError, UniFiClient

_LOGGER = logging.getLogger(__name__)


class UniFiAlertsCoordinator(DataUpdateCoordinator[dict[str, CategoryState]]):
    """Manages polling state and receives webhook-pushed alerts.

    - Polling: refreshes open_count per category every poll_interval seconds.
    - Webhooks: call push_alert() directly; this updates is_alerting immediately
      and schedules an auto-clear after clear_timeout minutes.
    - Entities subscribe to coordinator updates via the standard HA pattern.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: UniFiClient,
        config: dict[str, Any],
    ) -> None:
        poll_interval = config.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )
        self._client = client
        self._config = config
        self._clear_timeout_minutes: int = config.get(CONF_CLEAR_TIMEOUT, DEFAULT_CLEAR_TIMEOUT)
        self._enabled_categories: list[str] = config.get(CONF_ENABLED_CATEGORIES, ALL_CATEGORIES)
        self._site: str = config.get(CONF_SITE, DEFAULT_SITE)

        # Category state is long-lived; do NOT reset between coordinator refreshes
        self._category_states: dict[str, CategoryState] = {
            cat: CategoryState(category=cat, enabled=(cat in self._enabled_categories))
            for cat in ALL_CATEGORIES
        }

        # Tracks pending auto-clear tasks keyed by category
        self._clear_tasks: dict[str, asyncio.Task] = {}

    # ── DataUpdateCoordinator override ───────────────────────────────────

    async def _async_update_data(self) -> dict[str, CategoryState]:
        """Fetch open alarm counts from the controller (polling path)."""
        try:
            categorised = await self._client.categorise_alarms(self._site)
        except InvalidAuthError as err:
            # Re-authenticate once then retry
            _LOGGER.warning("Auth expired, re-authenticating: %s", err)
            try:
                await self._client.authenticate()
                categorised = await self._client.categorise_alarms(self._site)
            except (InvalidAuthError, CannotConnectError) as retry_err:
                raise UpdateFailed(f"UniFi auth failed: {retry_err}") from retry_err
        except CannotConnectError as err:
            raise UpdateFailed(f"Cannot reach UniFi controller: {err}") from err

        for cat, alerts in categorised.items():
            if cat in self._category_states:
                state = self._category_states[cat]
                if not state.enabled:
                    continue
                state.open_count = len(alerts)
                # If polling finds open alerts and we're not already alerting,
                # treat the most recent one as the active alert
                if alerts and not state.is_alerting:
                    most_recent = max(alerts, key=lambda a: a.received_at)
                    # Use direct assignment instead of apply_alert() so that
                    # poll-detected alerts do not increment alert_count.  Only
                    # webhook-pushed alerts (real new events) should do that.
                    state.is_alerting = True
                    state.last_alert = most_recent
                    self._schedule_clear(cat)

        # Zeroise open_count for enabled categories with no polled alarms
        for cat, state in self._category_states.items():
            if not state.enabled:
                continue
            if cat not in categorised:
                state.open_count = 0

        return self._category_states

    # ── Webhook push path ────────────────────────────────────────────────

    def push_alert(self, category: str, alert: UniFiAlert) -> None:
        """Called by the webhook handler when UniFi POSTs an alert.

        Updates category state immediately and notifies all subscribed entities.
        """
        if category not in self._category_states:
            _LOGGER.warning("push_alert called with unknown category: %s", category)
            return

        state = self._category_states[category]
        if not state.enabled:
            return

        state.apply_alert(alert)
        _LOGGER.debug("Alert pushed to category %s: %s", category, alert.message)

        # Cancel any existing clear timer and start a fresh one
        self._schedule_clear(category)

        # Notify all entities immediately — don't wait for the next poll
        self.async_set_updated_data(self._category_states)

    def get_category_state(self, category: str) -> CategoryState | None:
        return self._category_states.get(category)

    @property
    def category_states(self) -> dict[str, CategoryState]:
        return self._category_states

    @property
    def any_alerting(self) -> bool:
        return any(s.is_alerting for s in self._category_states.values() if s.enabled)

    @property
    def rollup_alert_count(self) -> int:
        return sum(s.alert_count for s in self._category_states.values() if s.enabled)

    @property
    def rollup_open_count(self) -> int:
        return sum(s.open_count for s in self._category_states.values() if s.enabled)

    @property
    def rollup_last_alert(self) -> UniFiAlert | None:
        alerts = [
            s.last_alert
            for s in self._category_states.values()
            if s.enabled and s.last_alert is not None
        ]
        if not alerts:
            return None
        return max(alerts, key=lambda a: a.received_at)

    # ── Auto-clear ───────────────────────────────────────────────────────

    def _schedule_clear(self, category: str) -> None:
        """Cancel any existing clear task and schedule a new one."""
        existing = self._clear_tasks.get(category)
        if existing and not existing.done():
            existing.cancel()

        delay = self._clear_timeout_minutes * 60
        self._clear_tasks[category] = self.hass.async_create_background_task(
            self._auto_clear(category, delay),
            name=f"unifi_alerts_auto_clear_{category}",
        )

    def cancel_clear(self, category: str) -> None:
        """Cancel any pending auto-clear task for the given category."""
        existing = self._clear_tasks.pop(category, None)
        if existing and not existing.done():
            existing.cancel()

    async def _auto_clear(self, category: str, delay_seconds: int) -> None:
        await asyncio.sleep(delay_seconds)
        state = self._category_states.get(category)
        if state and state.is_alerting:
            state.clear()
            _LOGGER.debug("Auto-cleared category %s after timeout", category)
            self.async_set_updated_data(self._category_states)

    async def async_shutdown(self) -> None:
        """Cancel all pending auto-clear tasks. Call during entry unload."""
        for task in self._clear_tasks.values():
            if not task.done():
                task.cancel()
        self._clear_tasks.clear()
