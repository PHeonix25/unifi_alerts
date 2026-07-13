"""Tests for UniFiAlertsCoordinator: polling path, error handling, v2 dispatch, unrecognised keys.

Split by behaviour area (#283) alongside test_push_dedup.py,
test_persistence.py, and test_autoclear.py in this package.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CATEGORY_NETWORK_WAN,
    CATEGORY_SECURITY_THREAT,
    CONF_CLEAR_TIMEOUT,
    CONF_ENABLED_CATEGORIES,
    CONF_MIN_SEVERITY,
    CONF_POLL_INTERVAL,
)
from custom_components.unifi_alerts.coordinator import UniFiAlertsCoordinator
from custom_components.unifi_alerts.models import UniFiAlert, ensure_aware
from custom_components.unifi_alerts.severity import MIN_SEVERITY_ORDER, SEVERITY_ORDER, meets_minimum

from .conftest import make_alert, make_full_coordinator, make_hass_and_client


class TestPollingPath:
    @pytest.mark.asyncio
    async def test_polling_does_not_increment_alert_count(self):
        """Polling open alarms must not increment alert_count — only webhooks should."""
        from custom_components.unifi_alerts.models import UniFiAlert

        hass, client = make_hass_and_client()
        polled_alert = UniFiAlert(
            category=CATEGORY_NETWORK_WAN,
            message="persistent open alarm",
            received_at=datetime(2024, 1, 1, 10, 0),
        )
        client.categorise_alarms = AsyncMock(return_value={CATEGORY_NETWORK_WAN: [polled_alert]})
        coord = make_full_coordinator(hass, client)

        # Simulate first poll — finds an open alarm
        await coord._async_update_data()
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.is_alerting is True
        assert state.alert_count == 0  # polling must NOT increment alert_count

    @pytest.mark.asyncio
    async def test_polling_does_not_fire_again_when_already_alerting(self):
        """If category is already alerting, polling must leave it unchanged."""
        from custom_components.unifi_alerts.models import UniFiAlert

        hass, client = make_hass_and_client()
        polled_alert = UniFiAlert(
            category=CATEGORY_NETWORK_WAN,
            message="open alarm",
            received_at=datetime(2024, 1, 1, 10, 0),
        )
        client.categorise_alarms = AsyncMock(return_value={CATEGORY_NETWORK_WAN: [polled_alert]})
        coord = make_full_coordinator(hass, client)

        # Mark as already alerting via webhook push (increments count to 1)
        webhook_alert = make_alert(CATEGORY_NETWORK_WAN, "webhook alert")
        coord.push_alert(CATEGORY_NETWORK_WAN, webhook_alert)
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.alert_count == 1

        # Poll again — should not increment count further
        await coord._async_update_data()
        assert state.alert_count == 1


class TestPollingErrorPaths:
    """Tests for _async_update_data error handling."""

    @pytest.mark.asyncio
    async def test_invalid_auth_triggers_re_auth_and_retries(self):
        """On InvalidAuthError the coordinator re-authenticates once and retries."""
        from custom_components.unifi_alerts.unifi_client import InvalidAuthError

        hass, client = make_hass_and_client()
        # First call raises InvalidAuthError; after re-auth the second call succeeds
        client.categorise_alarms = AsyncMock(side_effect=[InvalidAuthError("expired"), {}])
        client.authenticate = AsyncMock()
        coord = make_full_coordinator(hass, client)

        # Should not raise
        await coord._async_update_data()
        client.authenticate.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("categorise_side_effect", "authenticate_side_effect"),
        [
            pytest.param(
                "auth_error",
                "auth_error",
                id="reauth-itself-raises-invalid-auth",
            ),
            pytest.param(
                "auth_error",
                "cannot_connect",
                id="reauth-itself-raises-cannot-connect",
            ),
            pytest.param(
                "auth_error_twice",
                None,
                id="reauth-succeeds-but-retry-still-401",
            ),
        ],
    )
    async def test_reauth_failure_paths_raise_config_entry_auth_failed(
        self, categorise_side_effect, authenticate_side_effect
    ):
        """Every path that ends without a valid session must raise ConfigEntryAuthFailed.

        Covers: re-auth itself raising InvalidAuthError, re-auth itself raising
        CannotConnectError, and re-auth succeeding but the retried fetch still
        returning 401.
        """
        from homeassistant.exceptions import ConfigEntryAuthFailed

        from custom_components.unifi_alerts.unifi_client import CannotConnectError, InvalidAuthError

        categorise_effects = {
            "auth_error": InvalidAuthError("expired"),
            "auth_error_twice": [InvalidAuthError("expired"), InvalidAuthError("still 401")],
        }
        authenticate_effects = {
            None: None,
            "auth_error": InvalidAuthError("still bad"),
            "cannot_connect": CannotConnectError("unreachable during reauth"),
        }

        hass, client = make_hass_and_client()
        client.categorise_alarms = AsyncMock(side_effect=categorise_effects[categorise_side_effect])
        client.authenticate = AsyncMock(side_effect=authenticate_effects[authenticate_side_effect])
        coord = make_full_coordinator(hass, client)

        with pytest.raises(ConfigEntryAuthFailed):
            await coord._async_update_data()

        client.authenticate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reauth_succeeds_but_retry_fails_raises_update_failed_with_distinctive_message(
        self,
    ):
        """Re-auth succeeds but retried categorise_alarms fails → UpdateFailed with 'after re-authentication'."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        from custom_components.unifi_alerts.unifi_client import CannotConnectError, InvalidAuthError

        hass, client = make_hass_and_client()
        # First categorise_alarms call fails with auth error; re-auth succeeds; second call fails
        client.categorise_alarms = AsyncMock(
            side_effect=[InvalidAuthError("expired"), CannotConnectError("controller 500")]
        )
        client.authenticate = AsyncMock()  # re-auth succeeds
        coord = make_full_coordinator(hass, client)

        with pytest.raises(UpdateFailed) as exc_info:
            await coord._async_update_data()

        assert "after re-authentication" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_cannot_connect_raises_update_failed(self):
        """CannotConnectError must be wrapped in UpdateFailed."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        from custom_components.unifi_alerts.unifi_client import CannotConnectError

        hass, client = make_hass_and_client()
        client.categorise_alarms = AsyncMock(side_effect=CannotConnectError("timeout"))
        coord = make_full_coordinator(hass, client)

        with pytest.raises(UpdateFailed):
            await coord._async_update_data()

    @pytest.mark.asyncio
    async def test_polling_zeroes_open_count_for_cleared_categories(self):
        """Categories that have no polled alarms get open_count reset to 0."""
        hass, client = make_hass_and_client()
        # First poll: WAN has 1 alarm; second poll: WAN has 0 alarms
        polled_alert = UniFiAlert(
            category=CATEGORY_NETWORK_WAN,
            message="open",
            received_at=datetime(2024, 1, 1, 10, 0),
        )
        client.categorise_alarms = AsyncMock(
            side_effect=[
                {CATEGORY_NETWORK_WAN: [polled_alert]},
                {},  # second poll: nothing open
            ]
        )
        coord = make_full_coordinator(hass, client)

        await coord._async_update_data()
        assert coord.get_category_state(CATEGORY_NETWORK_WAN).open_count == 1

        await coord._async_update_data()
        assert coord.get_category_state(CATEGORY_NETWORK_WAN).open_count == 0


class TestSiteConfig:
    """Tests for CONF_SITE threading through the coordinator."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("site_configured", "expected_site"),
        [
            pytest.param("secondary", "secondary", id="explicit-site-forwarded"),
            pytest.param(None, "default", id="absent-site-defaults-to-default"),
        ],
    )
    async def test_coordinator_forwards_site_to_categorise_alarms(
        self, site_configured, expected_site
    ):
        """Coordinator must forward the configured site name (or 'default') to categorise_alarms."""
        from custom_components.unifi_alerts.const import CONF_SITE

        hass, client = make_hass_and_client()

        config = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_POLL_INTERVAL: 60,
            CONF_CLEAR_TIMEOUT: 30,
        }
        if site_configured is not None:
            config[CONF_SITE] = site_configured
        config_entry = MagicMock(entry_id="test-entry")
        coord = UniFiAlertsCoordinator(hass, client, config, config_entry)
        coord.async_set_updated_data = MagicMock()

        await coord._async_update_data()

        client.categorise_alarms.assert_awaited_once_with(expected_site)


class TestPollingWatermarkSuppressesIsAlerting:
    """Polling must apply the watermark filter when re-asserting is_alerting.

    Field-confirmed regression: after async_clear_category (or auto-clear)
    advanced last_cleared_at, the next poll re-discovered a pre-watermark
    alarm and re-asserted is_alerting=True with a stale message. The UI
    showed status=Problem + Open Count=0 simultaneously because open_count
    used the watermark filter but the is_alerting branch did not.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "scenario",
        ["pre-watermark-alarm-suppressed", "mixed-batch-picks-post-watermark-alarm"],
    )
    async def test_polling_applies_watermark_filter(self, scenario):
        """Polling must never re-assert is_alerting from a pre-watermark alarm.

        Covers the pure pre-watermark case (fully suppressed) and a mixed
        pre+post-watermark batch (only the post-watermark alarm counts).
        """
        hass, client = make_hass_and_client()

        watermark = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        stale = UniFiAlert(
            category=CATEGORY_NETWORK_WAN,
            message="stale pre-watermark alarm",
            received_at=datetime(2024, 6, 1, 11, 0, 0, tzinfo=UTC),
        )
        fresh = UniFiAlert(
            category=CATEGORY_NETWORK_WAN,
            message="fresh",
            received_at=datetime(2024, 6, 1, 13, 0, 0, tzinfo=UTC),
        )
        scenarios = {
            "pre-watermark-alarm-suppressed": ([stale], False, None, 0),
            "mixed-batch-picks-post-watermark-alarm": ([stale, fresh], True, fresh, 1),
        }
        alarms, expected_is_alerting, expected_last_alert, expected_open_count = scenarios[scenario]

        client.categorise_alarms = AsyncMock(return_value={CATEGORY_NETWORK_WAN: alarms})
        coord = make_full_coordinator(hass, client)
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        state.last_cleared_at = watermark

        await coord._async_update_data()

        assert state.is_alerting is expected_is_alerting
        assert state.last_alert is expected_last_alert
        assert state.open_count == expected_open_count


class TestCoordinatorV2Dispatch:
    """Tests for the v2 system-log dispatch path in _async_update_data."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        (
            "probe_return_value",
            "probe_side_effect",
            "expected_fetch_count",
            "expected_categorise_count",
        ),
        [
            pytest.param(True, None, 1, 0, id="system-log-available"),
            pytest.param(False, None, 0, 1, id="legacy-fallback-probe-false"),
            pytest.param(
                None,
                "cannot_connect",
                0,
                1,
                id="legacy-fallback-probe-exception",
            ),
            # Simulates the probe returning False due to a 404 (already handled
            # inside UniFiClient) - mechanically identical to the plain
            # probe-false case above, kept as its own id for traceability.
            pytest.param(False, None, 0, 1, id="legacy-fallback-404"),
        ],
    )
    async def test_coordinator_dispatches_on_probe_result(
        self, probe_return_value, probe_side_effect, expected_fetch_count, expected_categorise_count
    ):
        """The system-log probe result must select fetch_system_log_alarms vs categorise_alarms."""
        from custom_components.unifi_alerts.unifi_client import CannotConnectError

        side_effects = {None: None, "cannot_connect": CannotConnectError("network error")}

        hass, client = make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(
            return_value=probe_return_value, side_effect=side_effects[probe_side_effect]
        )
        client.fetch_system_log_alarms = AsyncMock(return_value=[])
        coord = make_full_coordinator(hass, client)

        await coord._async_update_data()

        assert client.fetch_system_log_alarms.await_count == expected_fetch_count
        assert client.categorise_alarms.await_count == expected_categorise_count

    @pytest.mark.asyncio
    async def test_v2_events_parsed_and_categorised(self):
        """v2 events returned from fetch_system_log_alarms must be parsed and grouped by category."""
        from custom_components.unifi_alerts.const import CATEGORY_SECURITY_THREAT

        hass, client = make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=True)
        client.fetch_system_log_alarms = AsyncMock(
            return_value=[
                {
                    "key": "THREAT_BLOCKED_KNOWN_DESTINATION_CLIENT",
                    "category": "SECURITY",
                    "status": "NEW",
                    "timestamp": 1778025612345,
                    "message_raw": "Threat from {SRC_IP}.",
                    "parameters": {"SRC_IP": {"name": "1.2.3.4"}},
                    "severity": "HIGH",
                },
                {
                    "key": "THREAT_BLOCKED_KNOWN_DESTINATION_CLIENT",
                    "category": "SECURITY",
                    "status": "NEW",
                    "timestamp": 1778025612000,
                    "message_raw": "Threat from {SRC_IP}.",
                    "parameters": {"SRC_IP": {"name": "5.6.7.8"}},
                    "severity": "HIGH",
                },
            ]
        )
        coord = make_full_coordinator(hass, client)

        await coord._async_update_data()

        state = coord.get_category_state(CATEGORY_SECURITY_THREAT)
        assert state.open_count == 2

    @pytest.mark.asyncio
    async def test_v2_unknown_key_with_unknown_category_is_skipped(self):
        """Events with no matching key or category enum must be silently skipped."""
        hass, client = make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=True)
        client.fetch_system_log_alarms = AsyncMock(
            return_value=[
                {
                    "key": "TOTALLY_UNKNOWN_KEY",
                    "category": "AUDIT",  # not in SYSTEM_LOG_CATEGORY_FALLBACK
                    "status": "NEW",
                    "timestamp": 1778025612345,
                    "message_raw": "Some audit event.",
                    "parameters": {},
                    "severity": "LOW",
                }
            ]
        )
        coord = make_full_coordinator(hass, client)

        await coord._async_update_data()

        # No category should have an open_count > 0
        for state in coord.category_states.values():
            assert state.open_count == 0

    @pytest.mark.asyncio
    async def test_v2_watermark_within_window_passed_as_since(self):
        """When the oldest watermark is within DEFAULT_SYSTEM_LOG_LOOKBACK_HOURS,
        it is passed as-is to fetch_system_log_alarms (no clamping needed)."""
        from datetime import UTC, datetime, timedelta

        from custom_components.unifi_alerts.const import DEFAULT_SYSTEM_LOG_LOOKBACK_HOURS

        hass, client = make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=True)
        client.fetch_system_log_alarms = AsyncMock(return_value=[])
        coord = make_full_coordinator(hass, client)

        # Place both watermarks within the lookback window
        now = datetime.now(UTC)
        older_wm = now - timedelta(hours=DEFAULT_SYSTEM_LOG_LOOKBACK_HOURS - 1)
        newer_wm = now - timedelta(hours=1)
        coord.get_category_state(CATEGORY_NETWORK_WAN).last_cleared_at = older_wm
        coord.get_category_state(CATEGORY_SECURITY_THREAT).last_cleared_at = newer_wm

        await coord._async_update_data()

        client.fetch_system_log_alarms.assert_awaited_once()
        _, kwargs = client.fetch_system_log_alarms.call_args
        # since must equal the older watermark (not clamped)
        assert kwargs.get("since") == older_wm

    @pytest.mark.asyncio
    async def test_v2_watermark_older_than_lookback_clamped(self):
        """When the oldest watermark is beyond DEFAULT_SYSTEM_LOG_LOOKBACK_HOURS,
        since= is clamped to now - DEFAULT_SYSTEM_LOG_LOOKBACK_HOURS."""
        from datetime import UTC, datetime, timedelta

        from custom_components.unifi_alerts.const import DEFAULT_SYSTEM_LOG_LOOKBACK_HOURS

        hass, client = make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=True)
        client.fetch_system_log_alarms = AsyncMock(return_value=[])
        coord = make_full_coordinator(hass, client)

        # Watermark far in the past (30 days ago) — well beyond the 24h cap
        stale_wm = datetime.now(UTC) - timedelta(days=30)
        coord.get_category_state(CATEGORY_NETWORK_WAN).last_cleared_at = stale_wm

        await coord._async_update_data()

        client.fetch_system_log_alarms.assert_awaited_once()
        _, kwargs = client.fetch_system_log_alarms.call_args
        since = kwargs.get("since")
        assert since is not None
        # since must NOT be the stale watermark; it must be approximately now - 24h
        expected_floor = datetime.now(UTC) - timedelta(hours=DEFAULT_SYSTEM_LOG_LOOKBACK_HOURS)
        # Allow 5-second tolerance for test execution time
        assert abs((since - expected_floor).total_seconds()) < 5

    @pytest.mark.asyncio
    async def test_v2_no_watermark_passes_none_as_since(self):
        """When no category has been cleared, since=None must be passed (client picks lookback)."""
        hass, client = make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=True)
        client.fetch_system_log_alarms = AsyncMock(return_value=[])
        coord = make_full_coordinator(hass, client)

        # No watermarks set; all last_cleared_at are None
        await coord._async_update_data()

        client.fetch_system_log_alarms.assert_awaited_once()
        _, kwargs = client.fetch_system_log_alarms.call_args
        assert kwargs.get("since") is None


class TestPollingSeverityGate:
    """Minimum_Severity_Setting gate on the polling path (_async_update_data)."""

    # Feature: minimum-severity-filter, Property 12: Severity-filtered polling drives
    # open_count, alerting selection, and the newest-seen watermark consistently
    @given(
        category=st.sampled_from(ALL_CATEGORIES),
        minimum=st.sampled_from(MIN_SEVERITY_ORDER),
        watermark_offset=st.one_of(st.none(), st.integers(min_value=-100_000, max_value=100_000)),
        alert_specs=st.lists(
            st.tuples(
                st.sampled_from(SEVERITY_ORDER),
                st.integers(min_value=-100_000, max_value=100_000),
            ),
            max_size=8,
        ),
    )
    @settings(max_examples=25, deadline=None)
    def test_severity_filtered_polling_drives_open_count_alerting_and_watermark(
        self,
        category: str,
        minimum: str,
        watermark_offset: int | None,
        alert_specs: list[tuple[str, int]],
    ) -> None:
        """open_count, is_alerting/last_alert selection, and the newest-seen
        watermark must all derive from the same severity-eligible subset,
        with open_count/is_alerting/last_alert further restricted to the
        watermark-eligible portion of that subset."""
        base_time = datetime(2024, 1, 1, tzinfo=UTC)
        watermark = (
            base_time + timedelta(seconds=watermark_offset) if watermark_offset is not None else None
        )
        alerts = [
            UniFiAlert(
                category=category,
                message=f"alert-{idx}",
                received_at=base_time + timedelta(seconds=offset),
                severity=severity,
            )
            for idx, (severity, offset) in enumerate(alert_specs)
        ]

        hass, client = make_hass_and_client()
        client.categorise_alarms = AsyncMock(return_value={category: alerts})
        coord = make_full_coordinator(hass, client)
        coord._config[CONF_MIN_SEVERITY] = {category: minimum}
        state = coord.get_category_state(category)
        state.last_cleared_at = watermark

        asyncio.run(coord._async_update_data())

        # Same severity-eligible subset feeds both open_count/alerting selection
        # (further restricted by the watermark) and the newest-seen watermark.
        eligible = [a for a in alerts if meets_minimum(a.severity_level, minimum)]
        counted = (
            [a for a in eligible if a.received_at > watermark] if watermark is not None else eligible
        )

        assert state.open_count == len(counted)

        if counted:
            expected_last_alert = max(counted, key=lambda a: a.received_at)
            assert state.is_alerting is True
            assert state.last_alert is expected_last_alert
        else:
            assert state.is_alerting is False
            assert state.last_alert is None

        if eligible:
            expected_newest_seen = max(ensure_aware(a.received_at) for a in eligible)
            assert state.last_alarm_received_at == expected_newest_seen
        else:
            assert state.last_alarm_received_at is None

    # Feature: minimum-severity-filter, Property 13: Disabled category is untouched
    # by a poll cycle regardless of severity content
    @given(
        category=st.sampled_from(ALL_CATEGORIES),
        minimum=st.sampled_from(MIN_SEVERITY_ORDER),
        prior_is_alerting=st.booleans(),
        prior_open_count=st.integers(min_value=0, max_value=1000),
        prior_last_alert_offset=st.one_of(
            st.none(), st.integers(min_value=-100_000, max_value=100_000)
        ),
        alert_specs=st.lists(
            st.tuples(
                st.sampled_from(SEVERITY_ORDER),
                st.integers(min_value=-100_000, max_value=100_000),
            ),
            max_size=8,
        ),
    )
    @settings(max_examples=25, deadline=None)
    def test_disabled_category_untouched_by_poll_cycle(
        self,
        category: str,
        minimum: str,
        prior_is_alerting: bool,
        prior_open_count: int,
        prior_last_alert_offset: int | None,
        alert_specs: list[tuple[str, int]],
    ) -> None:
        """A disabled category's is_alerting/last_alert/open_count must never be
        touched by a poll cycle, no matter what severities are polled or what
        Minimum_Severity_Setting is configured for it."""
        base_time = datetime(2024, 1, 1, tzinfo=UTC)
        prior_last_alert = (
            UniFiAlert(
                category=category,
                message="prior alert",
                received_at=base_time + timedelta(seconds=prior_last_alert_offset),
            )
            if prior_last_alert_offset is not None
            else None
        )
        alerts = [
            UniFiAlert(
                category=category,
                message=f"alert-{idx}",
                received_at=base_time + timedelta(seconds=offset),
                severity=severity,
            )
            for idx, (severity, offset) in enumerate(alert_specs)
        ]

        hass, client = make_hass_and_client()
        client.categorise_alarms = AsyncMock(return_value={category: alerts})
        coord = make_full_coordinator(hass, client)
        coord._config[CONF_MIN_SEVERITY] = {category: minimum}
        state = coord.get_category_state(category)
        state.enabled = False
        state.is_alerting = prior_is_alerting
        state.open_count = prior_open_count
        state.last_alert = prior_last_alert

        asyncio.run(coord._async_update_data())

        assert state.is_alerting is prior_is_alerting
        assert state.last_alert is prior_last_alert
        assert state.open_count == prior_open_count


class TestUnrecognisedKeys:
    """Coordinator must accumulate unrecognised event keys from both polling paths."""

    @pytest.mark.asyncio
    async def test_v2_unrecognised_key_accumulates_in_coordinator(self):
        """An unclassified v2 system-log key must be added to coordinator.unrecognised_keys."""
        hass, client = make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=True)
        client.fetch_system_log_alarms = AsyncMock(
            return_value=[
                {
                    "key": "TOTALLY_UNKNOWN_V2_KEY",
                    "category": "AUDIT",  # not in SYSTEM_LOG_CATEGORY_FALLBACK
                    "status": "NEW",
                    "timestamp": 1778025612345,
                    "message_raw": "Something happened.",
                    "parameters": {},
                    "severity": "LOW",
                }
            ]
        )
        coord = make_full_coordinator(hass, client)

        await coord._async_update_data()

        assert "TOTALLY_UNKNOWN_V2_KEY" in coord.unrecognised_keys
        assert coord.unrecognised_keys["TOTALLY_UNKNOWN_V2_KEY"] == 1

    @pytest.mark.asyncio
    async def test_v2_unrecognised_key_count_increments_across_polls(self):
        """Repeated unclassified keys accumulate counts across multiple polls."""
        hass, client = make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=True)
        event = {
            "key": "REPEATING_UNKNOWN_KEY",
            "category": "AUDIT",
            "status": "NEW",
            "timestamp": 1778025612345,
            "message_raw": ".",
            "parameters": {},
            "severity": "LOW",
        }
        client.fetch_system_log_alarms = AsyncMock(return_value=[event])
        coord = make_full_coordinator(hass, client)

        await coord._async_update_data()
        await coord._async_update_data()

        assert coord.unrecognised_keys["REPEATING_UNKNOWN_KEY"] == 2

    @pytest.mark.asyncio
    async def test_legacy_unrecognised_keys_merged_from_client(self):
        """On the legacy path, unrecognised keys from client.unrecognised_keys are merged."""
        hass, client = make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=False)
        client.categorise_alarms = AsyncMock(return_value={})
        # Simulate the client having tracked one unrecognised key from its last call.
        client.unrecognised_keys = {"EVT_MYSTERY_EVENT": 2}
        coord = make_full_coordinator(hass, client)

        await coord._async_update_data()

        assert "EVT_MYSTERY_EVENT" in coord.unrecognised_keys
        assert coord.unrecognised_keys["EVT_MYSTERY_EVENT"] == 2

    @pytest.mark.asyncio
    async def test_unrecognised_keys_empty_when_all_classified(self):
        """With no unclassified events, unrecognised_keys remains empty."""
        from custom_components.unifi_alerts.const import CATEGORY_SECURITY_THREAT

        hass, client = make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=True)
        client.fetch_system_log_alarms = AsyncMock(
            return_value=[
                {
                    "key": "THREAT_BLOCKED_KNOWN_DESTINATION_CLIENT",
                    "category": "SECURITY",
                    "status": "NEW",
                    "timestamp": 1778025612345,
                    "message_raw": "Threat from {SRC_IP}.",
                    "parameters": {"SRC_IP": {"name": "1.2.3.4"}},
                    "severity": "HIGH",
                }
            ]
        )
        coord = make_full_coordinator(hass, client)

        await coord._async_update_data()

        assert coord.unrecognised_keys == {}
        state = coord.get_category_state(CATEGORY_SECURITY_THREAT)
        assert state.open_count == 1
