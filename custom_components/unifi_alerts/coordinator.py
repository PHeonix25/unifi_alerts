"""DataUpdateCoordinator for UniFi Alerts."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Coroutine
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
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
    WEBHOOK_DEDUP_WINDOW_SECONDS,
)
from .models import CategoryState, UniFiAlert, UniFiClientConfig
from .unifi_client import CannotConnectError, InvalidAuthError, UniFiClient

_LOGGER = logging.getLogger(__name__)

_STORAGE_VERSION = 1

# Debounce window for watermark persistence. push_alert is synchronous and can
# fire in bursts; routing writes through Store.async_delay_save with this delay
# coalesces a burst into a single durable write instead of one fire-and-forget
# save per push.
_PERSIST_DELAY_SECONDS = 1

# Issue-registry id base for the repair surfaced when a watermark persist fails.
# Suffixed with the config entry id so multi-entry installs report independently.
_PERSIST_FAILED_ISSUE_BASE = "watermark_persist_failed"


class UniFiAlertsCoordinator(DataUpdateCoordinator[dict[str, CategoryState]]):
    """Manages polling state and receives webhook-pushed alerts.

    - Polling: refreshes open_count per category every poll_interval seconds.
      open_count is filtered to alarms newer than last_cleared_at (the
      acknowledgement watermark) so the count reflects "since last cleared"
      rather than a lifetime total.
    - Webhooks: call push_alert() directly; this updates is_alerting immediately
      and schedules an auto-clear after clear_timeout minutes.
    - Entities subscribe to coordinator updates via the standard HA pattern.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: UniFiClient,
        config: UniFiClientConfig,
        entry_id: str = "",
    ) -> None:
        poll_interval = config.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )
        self._client = client
        self._config: UniFiClientConfig = config
        self._clear_timeout_minutes: int = config.get(CONF_CLEAR_TIMEOUT, DEFAULT_CLEAR_TIMEOUT)
        self._enabled_categories: list[str] = config.get(CONF_ENABLED_CATEGORIES, ALL_CATEGORIES)
        self._site: str = config.get(CONF_SITE, DEFAULT_SITE)
        self._entry_id: str = entry_id
        self._store: Store[dict[str, Any]] = Store(
            hass, _STORAGE_VERSION, f"{DOMAIN}_watermarks_{entry_id}"
        )

        # Category state is long-lived; do NOT reset between coordinator refreshes
        self._category_states: dict[str, CategoryState] = {
            cat: CategoryState(category=cat, enabled=(cat in self._enabled_categories))
            for cat in ALL_CATEGORIES
        }

        # Tracks pending auto-clear tasks keyed by category
        self._clear_tasks: dict[str, asyncio.Task[None]] = {}

        # Deduplicates "unrecognised v2 system-log key" warnings per coordinator
        # instance. Instance-scoped rather than module-global so tests stay isolated.
        self._seen_unknown_keys: set[str] = set()

        # Per-(category, alert_key) monotonic timestamps of the last webhook
        # push that was actually applied. Subsequent pushes for the same pair
        # within WEBHOOK_DEDUP_WINDOW_SECONDS are dropped to prevent a noisy
        # controller from generating unbounded state updates and event fires.
        self._last_push_at: dict[tuple[str, str], float] = {}

        # Accumulates event keys seen during polling that could not be mapped to
        # any category. Exposed via diagnostics so users can report missing keys
        # without needing DEBUG logging. Never reset; grows until the entry reloads.
        self._unrecognised_keys: dict[str, int] = {}

    # ── DataUpdateCoordinator override ───────────────────────────────────

    async def _async_update_data(self) -> dict[str, CategoryState]:
        """Fetch open alarm counts from the controller (polling path).

        Dispatches to the v2 system-log endpoint when available (detected via
        a one-shot probe of /system-log/count). Falls back to the legacy
        /list/alarm path for older controllers or when the probe fails.

        Watermark policy for v2 polling:
          timestampFrom = the oldest last_cleared_at across all enabled
          categories (so we fetch everything since the oldest unacknowledged
          window). If no category has been cleared, fall back to now-24h.
          This is conservative: it over-fetches slightly but guarantees that
          recent alarms in every enabled category are always reachable.
        """
        try:
            categorised = await self._fetch_categorised()
        except InvalidAuthError as err:
            # Re-authenticate once then retry
            _LOGGER.warning("Auth expired, re-authenticating: %s", err)
            try:
                await self._client.authenticate()
            except (InvalidAuthError, CannotConnectError) as reauth_err:
                _LOGGER.error(
                    "Re-authentication failed; credentials may have changed: %s", reauth_err
                )
                raise ConfigEntryAuthFailed(
                    f"Re-authentication failed; credentials may have changed: {reauth_err}"
                ) from reauth_err
            try:
                categorised = await self._fetch_categorised()
            except InvalidAuthError as retry_err:
                raise ConfigEntryAuthFailed(
                    f"Re-authentication succeeded but the controller still returned 401: {retry_err}"
                ) from retry_err
            except CannotConnectError as retry_err:
                raise UpdateFailed(
                    f"Cannot reach UniFi controller after re-authentication: {retry_err}"
                ) from retry_err
        except CannotConnectError as err:
            raise UpdateFailed(f"Cannot reach UniFi controller: {err}") from err

        for cat, alerts in categorised.items():
            if cat in self._category_states:
                state = self._category_states[cat]
                if not state.enabled:
                    continue
                # Count only alarms newer than last_cleared_at so open_count reads as
                # "since last Clear", not a lifetime total.
                watermark = state.last_cleared_at
                counted = (
                    [a for a in alerts if a.received_at > watermark]
                    if watermark is not None
                    else alerts
                )
                state.open_count = len(counted)
                # If polling finds open alerts and we're not already alerting,
                # treat the most recent one as the active alert. Use the
                # watermark-filtered list so a stale pre-Clear alarm cannot
                # re-assert is_alerting after auto-clear (UI would otherwise
                # show Problem + Open Count=0 simultaneously).
                if counted and not state.is_alerting:
                    most_recent = max(counted, key=lambda a: a.received_at)
                    # Polling sets is_alerting directly without incrementing alert_count; that counter
                    # is webhook-only so event entities only fire on real pushes, not poll reconciliation.
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

    async def _fetch_categorised(self) -> dict[str, list[UniFiAlert]]:
        """Fetch and categorise alarms using v2 or legacy path as appropriate.

        Calls probe_system_log_endpoint() once per client instance. On success,
        fetches from system-log/all with a timestampFrom watermark and parses
        each event with UniFiAlert.from_system_log_event(). Skips events whose
        resolved category is empty (unknown keys with no broad enum fallback).

        Falls back to legacy categorise_alarms() if:
          - the probe returns False (404 / 4xx from the controller)
          - the probe itself raises a network error (logged at DEBUG)
          - this is an older controller without the v2 endpoint
        """
        try:
            has_v2 = await self._client.probe_system_log_endpoint(self._site)
        except Exception as probe_err:  # noqa: BLE001
            _LOGGER.debug(
                "v2 system-log probe raised %s; falling back to legacy path",
                type(probe_err).__name__,
            )
            has_v2 = False

        if not has_v2:
            result = await self._client.categorise_alarms(self._site)
            for key, count in self._client.unrecognised_keys.items():
                self._unrecognised_keys[key] = self._unrecognised_keys.get(key, 0) + count
            return result

        # v2 path: compute the oldest watermark across enabled categories so we
        # fetch everything since the oldest unacknowledged window.
        watermarks = [
            state.last_cleared_at
            for state in self._category_states.values()
            if state.enabled and state.last_cleared_at is not None
        ]
        since: datetime | None = min(watermarks) if watermarks else None

        raw_events = await self._client.fetch_system_log_alarms(self._site, since=since)

        categorised: dict[str, list[UniFiAlert]] = {}
        for event in raw_events:
            alert = UniFiAlert.from_system_log_event(event, self._seen_unknown_keys)
            if not alert.category:
                # Unknown key and no broad enum fallback — skip, same as legacy behaviour
                key = event.get("key", "")
                if key:
                    self._unrecognised_keys[key] = self._unrecognised_keys.get(key, 0) + 1
                    _LOGGER.debug(
                        "Unclassified v2 system-log event key %r — consider reporting it at "
                        "https://github.com/PHeonix25/unifi_alerts/issues",
                        key,
                    )
                continue
            categorised.setdefault(alert.category, []).append(alert)

        return categorised

    # ── Webhook push path ────────────────────────────────────────────────

    def push_alert(self, category: str, alert: UniFiAlert) -> None:
        """Called by the webhook handler when UniFi POSTs an alert.

        Updates category state immediately and notifies all subscribed entities.
        Duplicate ``(category, alert.key)`` pairs received within
        ``WEBHOOK_DEDUP_WINDOW_SECONDS`` are dropped — without this, a
        misconfigured Alarm Manager or noisy category can flood the webhook
        endpoint and cause unbounded ``alert_count`` increments and event
        entity fires for the same underlying event.
        """
        if category not in self._category_states:
            _LOGGER.warning("push_alert called with unknown category: %s", category)
            return

        state = self._category_states[category]
        if not state.enabled:
            return

        dedup_key = (category, alert.key or "")
        now = time.monotonic()
        # Absorbs duplicate webhook deliveries from the controller within the window;
        # monotonic time makes the window immune to clock skew during HA suspend/resume.
        prev = self._last_push_at.get(dedup_key)
        if prev is not None and (now - prev) < WEBHOOK_DEDUP_WINDOW_SECONDS:
            _LOGGER.debug(
                "Suppressing duplicate webhook push for %s/%s within %.1fs window",
                category,
                dedup_key[1],
                WEBHOOK_DEDUP_WINDOW_SECONDS,
            )
            return
        # Opportunistically drop expired entries before recording the new one.
        # Bounds the dict size at "distinct (category, alert_key) pairs seen
        # within the last WEBHOOK_DEDUP_WINDOW_SECONDS" — a misconfigured
        # controller emitting high-cardinality keys cannot grow it without
        # bound. Cost is O(n) per push, but n is naturally small (capped by
        # the active windowed set).
        cutoff = now - WEBHOOK_DEDUP_WINDOW_SECONDS
        self._last_push_at = {k: t for k, t in self._last_push_at.items() if t >= cutoff}
        self._last_push_at[dedup_key] = now

        state.apply_alert(alert)
        # Record webhook receipt for the per-category health signal. Set only
        # here (the push path), never by polling, so it reflects webhook
        # connectivity specifically. alert.received_at is the receipt time
        # stamped by the webhook handler.
        state.last_webhook_at = alert.received_at
        # Optimistic open_count increment so the count sensor moves with the
        # binary sensor instead of lagging by up to one poll interval. Only
        # count alerts received after the watermark — anything older was
        # already acknowledged. Polling reconciles to the authoritative value
        # on the next refresh (clamps down if this push has since cleared).
        if state.last_cleared_at is None or alert.received_at > state.last_cleared_at:
            state.open_count += 1
        _LOGGER.debug("Alert pushed to category %s: %s", category, alert.message)

        # Persist alert_count and last_alert so they survive a config-entry
        # reload triggered by an options change. Scheduled as a background
        # task because push_alert is synchronous.
        self._schedule_persist()

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
    def unrecognised_keys(self) -> dict[str, int]:
        """Event keys seen during polling that could not be mapped to any category.

        Keys accumulate across all polls since the config entry was loaded. Exposed
        via diagnostics so users can report missing keys without enabling DEBUG logging.
        """
        return self._unrecognised_keys

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

    # ── Watermark persistence ─────────────────────────────────────────────

    async def async_restore_watermarks(self) -> None:
        """Load persisted category state from storage on startup.

        Restores ``last_cleared_at``, ``alert_count``, and ``last_alert`` for
        each category. Legacy payloads that only contain ``last_cleared_at``
        (a plain ISO string, pre-v1.6.0) are handled transparently: the dict
        branch runs when the stored value is a dict; the string branch handles
        the old format so existing installs are not disrupted.
        """
        data: dict[str, Any] | None = await self._store.async_load()
        if not data:
            return
        for cat, entry in data.items():
            state = self._category_states.get(cat)
            if state is None:
                continue
            if isinstance(entry, str):
                # Legacy format: bare ISO string watermark only.
                try:
                    state.last_cleared_at = datetime.fromisoformat(entry)
                except (ValueError, TypeError):
                    _LOGGER.warning("Ignoring invalid stored watermark for %s: %r", cat, entry)
            elif isinstance(entry, dict):
                ts_str = entry.get("last_cleared_at")
                if ts_str is not None:
                    try:
                        state.last_cleared_at = datetime.fromisoformat(ts_str)
                    except (ValueError, TypeError):
                        _LOGGER.warning("Ignoring invalid stored watermark for %s: %r", cat, ts_str)
                state.alert_count = int(entry.get("alert_count", 0))
                raw_alert = entry.get("last_alert")
                if raw_alert is not None:
                    try:
                        state.last_alert = UniFiAlert.from_dict(raw_alert)
                    except (KeyError, TypeError, ValueError):
                        _LOGGER.warning("Ignoring invalid stored last_alert for %s", cat)
                webhook_ts = entry.get("last_webhook_at")
                if webhook_ts is not None:
                    try:
                        state.last_webhook_at = datetime.fromisoformat(webhook_ts)
                    except (ValueError, TypeError):
                        _LOGGER.warning(
                            "Ignoring invalid stored last_webhook_at for %s: %r", cat, webhook_ts
                        )

    def _build_persist_data(self) -> dict[str, Any]:
        """Build the JSON-serialisable snapshot of category state to persist.

        Synchronous so it can be handed to ``Store.async_delay_save`` as the
        data function, which calls it at write time to capture the latest
        state after a burst of pushes has settled.
        """
        data: dict[str, Any] = {}
        for cat, state in self._category_states.items():
            entry: dict[str, Any] = {}
            if state.last_cleared_at is not None:
                entry["last_cleared_at"] = state.last_cleared_at.isoformat()
            entry["alert_count"] = state.alert_count
            entry["last_alert"] = (
                state.last_alert.to_dict() if state.last_alert is not None else None
            )
            if state.last_webhook_at is not None:
                entry["last_webhook_at"] = state.last_webhook_at.isoformat()
            data[cat] = entry
        return data

    async def _async_persist_watermarks(self) -> None:
        """Persist current category state immediately (awaited explicit-clear path).

        On failure (disk full, I/O error) the in-memory clear has already
        succeeded, so the user sees the alert cleared but the watermark never
        reaches disk. On the next HA restart open_count jumps back to the
        pre-clear value. Surface this as a repair issue so the loss is visible
        instead of buried in the log, then re-raise so the caller's error path
        (including the background-task done-callback) still runs. A subsequent
        successful persist deletes the issue, so it self-heals.
        """
        try:
            await self._store.async_save(self._build_persist_data())
        except Exception:
            self._create_persist_failed_issue()
            raise
        else:
            self._delete_persist_failed_issue()

    @property
    def _persist_failed_issue_id(self) -> str:
        """Per-entry issue-registry id for the watermark-persist-failed repair."""
        return f"{_PERSIST_FAILED_ISSUE_BASE}_{self._entry_id}"

    def _create_persist_failed_issue(self) -> None:
        """Raise a repair issue telling the user a watermark write failed."""
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._persist_failed_issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=_PERSIST_FAILED_ISSUE_BASE,
        )

    def _delete_persist_failed_issue(self) -> None:
        """Clear the watermark-persist-failed repair once a write succeeds."""
        ir.async_delete_issue(self.hass, DOMAIN, self._persist_failed_issue_id)

    # ── Clear entry points (called by buttons and services) ───────────────

    async def async_clear_category(self, category: str) -> None:
        """Clear a single category: set watermark, cancel auto-clear, notify."""
        state = self._category_states.get(category)
        if state is None:
            return
        self.cancel_clear(category)
        state.clear()
        await self._async_persist_watermarks()
        self.async_set_updated_data(self._category_states)
        _LOGGER.debug("Cleared category %s; watermark set to %s", category, state.last_cleared_at)

    async def async_clear_all(self) -> None:
        """Clear all enabled categories: set watermarks, cancel all auto-clears, notify once."""
        for category, state in self._category_states.items():
            if not state.enabled:
                continue
            self.cancel_clear(category)
            state.clear()
        await self._async_persist_watermarks()
        self.async_set_updated_data(self._category_states)
        _LOGGER.debug("Cleared all categories")

    # ── Auto-clear ───────────────────────────────────────────────────────

    def _schedule_clear(self, category: str) -> None:
        """Cancel any existing clear task and schedule a new one."""
        existing = self._clear_tasks.get(category)
        if existing and not existing.done():
            existing.cancel()

        delay = self._clear_timeout_minutes * 60
        self._clear_tasks[category] = self._run_background(
            self._auto_clear(category, delay),
            name=f"unifi_alerts_auto_clear_{category}",
        )

    def _run_background(self, coro: Coroutine[Any, Any, None], *, name: str) -> asyncio.Task[None]:
        """Create a background task and surface any exception it raises.

        Centralises background-task creation so a failure in a fire-and-forget
        coroutine (e.g. the persist awaited inside ``_auto_clear``) is logged
        via the done-callback instead of being silently swallowed.
        """
        create_bg = getattr(self.hass, "async_create_background_task", None)
        task: asyncio.Task[None]
        if create_bg is not None:
            task = create_bg(coro, name=name)
        else:
            create_task = getattr(self.hass, "async_create_task", None)
            task = create_task(coro) if create_task is not None else asyncio.ensure_future(coro)
        task.add_done_callback(self._on_background_task_done)
        return task

    @staticmethod
    def _on_background_task_done(task: asyncio.Task[Any]) -> None:
        """Log any non-cancellation exception raised by a background task."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            _LOGGER.error("Background task %s failed: %s", task.get_name(), exc, exc_info=exc)

    def _schedule_persist(self) -> None:
        """Persist category state, coalescing bursts into one delayed write.

        push_alert is synchronous and can fire rapidly. Routing through
        ``Store.async_delay_save`` debounces a burst into a single durable
        write (no lost-update race between overlapping fire-and-forget saves)
        and lets HA's storage layer own the write and log any failure.
        """
        self._store.async_delay_save(self._build_persist_data, _PERSIST_DELAY_SECONDS)

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
            # Persist the watermark advanced by clear() so an HA restart
            # immediately after auto-clear does not lose it (which would
            # cause open_count to jump back to the lifetime total).
            await self._async_persist_watermarks()
            _LOGGER.debug("Auto-cleared category %s after timeout", category)
            self.async_set_updated_data(self._category_states)

    async def async_shutdown(self) -> None:
        """Cancel all pending auto-clear tasks. Call during entry unload."""
        for task in self._clear_tasks.values():
            if not task.done():
                task.cancel()
        self._clear_tasks.clear()
