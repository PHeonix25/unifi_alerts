"""Tests for the Minimum_Severity_Setting selector in Config_Flow and Options_Flow.

Covers Properties 5-6 (categories-step submission round-tripping) from
design.md's Correctness Properties section, plus the associated Options_Flow
pre-fill example test (10.4). Split from test_setup.py (which owns the
existing category-enable/disable and generic categories-step behavior) since
this file is scoped specifically to the min_severity_{category} selector
added by this feature.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from custom_components.unifi_alerts.config_flow import UniFiAlertsOptionsFlow
from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CONF_ENABLED_CATEGORIES,
    CONF_MIN_SEVERITY,
    CONF_WEBHOOK_SECRET,
)
from custom_components.unifi_alerts.severity import MIN_SEVERITY_NO_FILTER, MIN_SEVERITY_ORDER

from .conftest import _VALID_INPUT, make_flow, make_options_flow


class TestConfigFlowMinSeverity:
    """Property 5: Config_Flow categories-step submission round-trips per
    category, defaulting omitted categories to No_Filter."""

    # Feature: minimum-severity-filter, Property 5: Config_Flow categories-step
    # submission round-trips per category, defaulting omitted categories to No_Filter
    @given(
        submitted=st.dictionaries(
            keys=st.sampled_from(ALL_CATEGORIES),
            values=st.sampled_from(MIN_SEVERITY_ORDER),
            max_size=len(ALL_CATEGORIES),
        )
    )
    @settings(max_examples=25, deadline=None)
    def test_categories_step_submission_round_trips_per_category(
        self, submitted: dict[str, str]
    ) -> None:
        """Submitting the categories step with an arbitrary subset-to-setting
        mapping must store the submitted value for every category present in
        the mapping, and No_Filter for every category omitted from it."""

        async def _run() -> dict[str, str]:
            flow = make_flow()
            flow._controller_url = "https://192.168.1.1"
            flow._detected_auth_method = "userpass"
            flow._credentials = dict(_VALID_INPUT)
            # async_step_finish needs a real hass to render webhook URLs; the
            # submission-round-trip behavior under test is fully captured by
            # _entry_data before that step runs, so it is mocked out here the
            # same way test_setup.py's TestCategoriesStep does.
            flow.async_step_finish = AsyncMock(return_value={"type": "form", "step_id": "finish"})

            # At least one category must be enabled or the step re-shows the
            # form with an error instead of proceeding to store _entry_data.
            cat_input: dict[str, object] = {f"cat_{cat}": True for cat in ALL_CATEGORIES}
            for cat, value in submitted.items():
                cat_input[f"min_severity_{cat}"] = value

            await flow.async_step_categories(cat_input)
            return flow._entry_data[CONF_MIN_SEVERITY]

        stored = asyncio.run(_run())

        expected = {cat: submitted.get(cat, MIN_SEVERITY_NO_FILTER) for cat in ALL_CATEGORIES}
        assert stored == expected


class TestOptionsFlowMinSeverity:
    """Property 6: Options_Flow categories-step submission round-trips
    independent of pre-fill."""

    # Feature: minimum-severity-filter, Property 6: Options_Flow categories-step
    # submission round-trips independent of pre-fill
    @given(
        stored=st.dictionaries(
            keys=st.sampled_from(ALL_CATEGORIES),
            values=st.sampled_from(MIN_SEVERITY_ORDER),
            max_size=len(ALL_CATEGORIES),
        ),
        submitted=st.dictionaries(
            keys=st.sampled_from(ALL_CATEGORIES),
            values=st.sampled_from(MIN_SEVERITY_ORDER),
            max_size=len(ALL_CATEGORIES),
        ),
    )
    @settings(max_examples=25, deadline=None)
    def test_categories_step_submission_round_trips_independent_of_prefill(
        self, stored: dict[str, str], submitted: dict[str, str]
    ) -> None:
        """Submitting the options-flow categories step must persist exactly the
        submitted per-category mapping (omitted categories defaulting to
        No_Filter), regardless of what was previously stored/pre-filled."""

        async def _run() -> dict[str, str]:
            config_entry = MagicMock()
            config_entry.entry_id = "entry-options-min-severity"
            # The previously-stored mapping — used only to pre-fill the form
            # when user_input is None. It must have no bearing on what a
            # concrete submission persists.
            config_entry.data = {
                CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
                CONF_WEBHOOK_SECRET: "s",
                CONF_MIN_SEVERITY: stored,
            }
            config_entry.options = {}

            flow = UniFiAlertsOptionsFlow(config_entry)
            flow.hass = MagicMock()
            # async_step_finish needs a real hass to render webhook URLs; the
            # submission-round-trip behavior under test is fully captured by
            # _pending_options before that step runs, same as
            # TestConfigFlowMinSeverity above.
            flow.async_step_finish = AsyncMock(return_value={"type": "form", "step_id": "finish"})

            # At least one category must be enabled or the step re-shows the
            # form with an error instead of storing _pending_options.
            cat_input: dict[str, object] = {f"cat_{cat}": True for cat in ALL_CATEGORIES}
            for cat, value in submitted.items():
                cat_input[f"min_severity_{cat}"] = value

            await flow.async_step_categories(cat_input)
            return flow._pending_options[CONF_MIN_SEVERITY]

        persisted = asyncio.run(_run())

        expected = {cat: submitted.get(cat, MIN_SEVERITY_NO_FILTER) for cat in ALL_CATEGORIES}
        assert persisted == expected

    # Feature: minimum-severity-filter, Task 10.4: Options_Flow categories-step
    # pre-fill (mandatory unit test, not a property test)
    def test_categories_step_prefill_legacy_entry_defaults_to_no_filter(self) -> None:
        """A legacy entry with no stored `min_severity` in either `.options` or
        `.data` must pre-fill every category's selector to No_Filter."""
        flow = make_options_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "categories"})

        asyncio.run(flow.async_step_categories(None))

        call_kwargs = flow.async_show_form.call_args.kwargs
        schema = call_kwargs["data_schema"]
        markers_by_name = {str(k): k for k in schema.schema}

        for cat in ALL_CATEGORIES:
            marker = markers_by_name[f"min_severity_{cat}"]
            assert marker.default() == MIN_SEVERITY_NO_FILTER

    def test_categories_step_prefill_resolves_stored_value(self) -> None:
        """An entry with an explicit stored `min_severity` value for a category
        must pre-fill that category's selector with the stored value, while
        other categories still default to No_Filter."""
        stored_cat = ALL_CATEGORIES[0]
        stored_value = next(v for v in MIN_SEVERITY_ORDER if v != MIN_SEVERITY_NO_FILTER)

        flow = make_options_flow()
        flow._config_entry.data[CONF_MIN_SEVERITY] = {stored_cat: stored_value}
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "categories"})

        asyncio.run(flow.async_step_categories(None))

        call_kwargs = flow.async_show_form.call_args.kwargs
        schema = call_kwargs["data_schema"]
        markers_by_name = {str(k): k for k in schema.schema}

        stored_marker = markers_by_name[f"min_severity_{stored_cat}"]
        assert stored_marker.default() == stored_value

        for cat in ALL_CATEGORIES:
            if cat == stored_cat:
                continue
            marker = markers_by_name[f"min_severity_{cat}"]
            assert marker.default() == MIN_SEVERITY_NO_FILTER
