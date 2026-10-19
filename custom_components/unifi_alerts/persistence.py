"""Persistence of per-category acknowledgement state for UniFi Alerts.

``WatermarkStore`` owns every interaction with Home Assistant's ``Store`` for a
config entry: the storage key and version, the on-disk snapshot format, the
tolerant restore (including the pre-v1.6.0 bare-string format), the debounced
and immediate write paths, and the "watermark persist failed" repair issue.
The coordinator owns the in-memory ``CategoryState`` objects and delegates all
storage bookkeeping here (#386).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store

from .const import DOMAIN, ISSUE_ID_PERSIST_FAILED, STORAGE_VERSION_WATERMARKS
from .models import CategoryState, UniFiAlert, ensure_aware

_LOGGER = logging.getLogger(__name__)

# Debounce window for watermark persistence. push_alert is synchronous and can
# fire in bursts; routing writes through Store.async_delay_save with this delay
# coalesces a burst into a single durable write instead of one fire-and-forget
# save per push.
_PERSIST_DELAY_SECONDS = 1


def _new_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    """Build the per-entry watermark ``Store`` (single source of key and version)."""
    return Store(hass, STORAGE_VERSION_WATERMARKS, f"{DOMAIN}_watermarks_{entry_id}")


async def async_remove_watermarks(hass: HomeAssistant, entry_id: str) -> None:
    """Delete the persisted watermark file for a removed config entry."""
    await _new_store(hass, entry_id).async_remove()


class WatermarkStore:
    """Load and save the coordinator's per-category state for one config entry.

    Holds a live reference to the coordinator's ``category_states`` mapping (it
    is long-lived and never reassigned), so every write captures the current
    state at write time. Restoring mutates the same ``CategoryState`` objects
    in place.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        category_states: dict[str, CategoryState],
    ) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._category_states = category_states
        self._store: Store[dict[str, Any]] = _new_store(hass, entry_id)

    async def load(self) -> None:
        """Load persisted category state from storage on startup.

        Restores ``last_cleared_at``, ``alert_count``, ``last_alert`` and
        ``last_webhook_at`` for each category. Legacy payloads that only contain
        ``last_cleared_at`` (a plain ISO string, pre-v1.6.0) are handled
        transparently: the dict branch runs when the stored value is a dict;
        the string branch handles the old format so existing installs are not
        disrupted.
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
                    state.last_cleared_at = ensure_aware(datetime.fromisoformat(entry))
                except ValueError, TypeError:
                    _LOGGER.warning("Ignoring invalid stored watermark for %s: %r", cat, entry)
            elif isinstance(entry, dict):
                ts_str = entry.get("last_cleared_at")
                if ts_str is not None:
                    try:
                        state.last_cleared_at = ensure_aware(datetime.fromisoformat(ts_str))
                    except ValueError, TypeError:
                        _LOGGER.warning("Ignoring invalid stored watermark for %s: %r", cat, ts_str)
                state.alert_count = int(entry.get("alert_count", 0))
                raw_alert = entry.get("last_alert")
                if raw_alert is not None:
                    try:
                        state.last_alert = UniFiAlert.from_dict(raw_alert)
                    except KeyError, TypeError, ValueError:
                        _LOGGER.warning("Ignoring invalid stored last_alert for %s", cat)
                webhook_ts = entry.get("last_webhook_at")
                if webhook_ts is not None:
                    try:
                        state.last_webhook_at = ensure_aware(datetime.fromisoformat(webhook_ts))
                    except ValueError, TypeError:
                        _LOGGER.warning(
                            "Ignoring invalid stored last_webhook_at for %s: %r", cat, webhook_ts
                        )

    def build_data(self) -> dict[str, Any]:
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

    async def save(self) -> None:
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
            await self._store.async_save(self.build_data())
        except Exception:
            self._create_persist_failed_issue()
            raise
        else:
            self._delete_persist_failed_issue()

    def schedule_save(self) -> None:
        """Persist category state, coalescing bursts into one delayed write.

        push_alert is synchronous and can fire rapidly. Routing through
        ``Store.async_delay_save`` debounces a burst into a single durable
        write (no lost-update race between overlapping fire-and-forget saves)
        and lets HA's storage layer own the write and log any failure.
        """
        self._store.async_delay_save(self.build_data, _PERSIST_DELAY_SECONDS)

    @property
    def _persist_failed_issue_id(self) -> str:
        """Per-entry issue-registry id for the watermark-persist-failed repair."""
        return f"{ISSUE_ID_PERSIST_FAILED}_{self._entry_id}"

    def _create_persist_failed_issue(self) -> None:
        """Raise a repair issue telling the user a watermark write failed."""
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            self._persist_failed_issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_ID_PERSIST_FAILED,
        )

    def _delete_persist_failed_issue(self) -> None:
        """Clear the watermark-persist-failed repair once a write succeeds."""
        ir.async_delete_issue(self._hass, DOMAIN, self._persist_failed_issue_id)
