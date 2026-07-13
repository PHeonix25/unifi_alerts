"""Property-based tests for severity normalization (custom_components/unifi_alerts/severity.py)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from custom_components.unifi_alerts.const import CONF_MIN_SEVERITY
from custom_components.unifi_alerts.models import UniFiAlert
from custom_components.unifi_alerts.severity import (
    _SEVERITY_SYNONYMS,
    MIN_SEVERITY_NO_FILTER,
    MIN_SEVERITY_ORDER,
    SEVERITY_LOW,
    SEVERITY_ORDER,
    get_effective_min_severity,
    normalize_severity,
)

_CANONICAL_NAMES: list[str] = list(SEVERITY_ORDER)
_CANONICAL_NAMES_LOWER: set[str] = {name.lower() for name in _CANONICAL_NAMES}
_SYNONYM_KEYS: list[str] = list(_SEVERITY_SYNONYMS.keys())
_ALL_MATCHED_NAMES: list[str] = _CANONICAL_NAMES + _SYNONYM_KEYS

# Whitespace characters used to pad canonical/synonym names when testing
# whitespace-insensitivity. Kept to a small, deliberate set of ASCII/Unicode
# whitespace rather than sampling st.text() for padding, since the property
# under test is about matching, not about exercising exotic whitespace.
_WHITESPACE_CHARS: list[str] = [" ", "\t", "\n", "\u00a0"]


def _case_variants(name: str) -> st.SearchStrategy[str]:
    """Strategy producing arbitrary per-character casing variants of `name`."""
    return st.tuples(*[st.sampled_from([ch.lower(), ch.upper()]) for ch in name]).map(
        lambda chars: "".join(chars)
    )


def _padded(name: str) -> st.SearchStrategy[str]:
    """Strategy producing `name` with arbitrary leading/trailing whitespace padding."""
    whitespace = st.text(alphabet=_WHITESPACE_CHARS, max_size=5)
    return st.tuples(whitespace, whitespace).map(lambda pad: f"{pad[0]}{name}{pad[1]}")


# Normalizer totality: normalize_severity must be a total function over
# arbitrary string input, never raising and never returning the sentinel.
@given(raw=st.text())
@settings(max_examples=25)
def test_normalize_severity_totality(raw: str) -> None:
    """normalize_severity always returns one of the four Severity_Levels,
    and never the MIN_SEVERITY_NO_FILTER sentinel, for any string input."""
    result = normalize_severity(raw)
    assert result in SEVERITY_ORDER
    assert result != MIN_SEVERITY_NO_FILTER


# Canonical and synonym matching must be case- and whitespace-insensitive.
@given(
    name=st.sampled_from(_ALL_MATCHED_NAMES),
    data=st.data(),
)
@settings(max_examples=25)
def test_normalize_severity_case_and_whitespace_insensitive(name: str, data: st.DataObject) -> None:
    """Any casing/whitespace-padding variant of a canonical name or documented
    synonym must normalize to the Severity_Level that name/synonym maps to."""
    cased = data.draw(_case_variants(name))
    padded = data.draw(_padded(cased))

    expected = _SEVERITY_SYNONYMS.get(name, name)

    assert normalize_severity(padded) == expected


# Unmatched or empty input must fall back to LOW.
@given(
    raw=st.text().filter(
        lambda s: (
            s.strip().lower() not in _CANONICAL_NAMES_LOWER
            and s.strip().lower() not in _SEVERITY_SYNONYMS
        )
    )
)
@settings(max_examples=25)
def test_normalize_severity_unmatched_or_empty_falls_back_to_low(raw: str) -> None:
    """Any string that, after lowercasing and stripping, does not match a
    canonical Severity_Level name or a documented synonym key (including the
    empty string) must normalize to SEVERITY_LOW."""
    assert normalize_severity(raw) == SEVERITY_LOW


# Effective-setting resolution must default missing data to No_Filter.
@given(
    category=st.text(min_size=1),
    other_categories=st.dictionaries(st.text(min_size=1), st.sampled_from(MIN_SEVERITY_ORDER)),
    stored_value=st.sampled_from(MIN_SEVERITY_ORDER),
)
@settings(max_examples=25)
def test_get_effective_min_severity_defaults_missing_data_to_no_filter(
    category: str,
    other_categories: dict[str, str],
    stored_value: str,
) -> None:
    """get_effective_min_severity resolves to MIN_SEVERITY_NO_FILTER when the
    min_severity map is absent entirely, and also when the map is present but
    missing the specific category's key. When the map is present and has the
    category's key set, it resolves to that stored value."""
    other_categories.pop(category, None)

    # Case 1: min_severity map absent entirely from config.
    config_without_map: dict[str, Any] = {}
    assert get_effective_min_severity(config_without_map, category) == MIN_SEVERITY_NO_FILTER

    # Case 2: min_severity map present but missing the specific category key.
    config_missing_key: dict[str, Any] = {CONF_MIN_SEVERITY: dict(other_categories)}
    assert get_effective_min_severity(config_missing_key, category) == MIN_SEVERITY_NO_FILTER

    # Case 3: min_severity map present with the category key set to an
    # arbitrary valid value from MIN_SEVERITY_ORDER.
    config_with_key: dict[str, Any] = {
        CONF_MIN_SEVERITY: {**other_categories, category: stored_value}
    }
    assert get_effective_min_severity(config_with_key, category) == stored_value


# Raw severity must be preserved independent of normalization.
@given(raw=st.text())
@settings(max_examples=25)
def test_alert_severity_preserved_independent_of_normalization(raw: str) -> None:
    """Constructing a UniFiAlert directly stores `severity` verbatim (no
    truncation occurs in __init__ - the 32-char truncation only happens in
    the from_webhook_payload/from_api_alarm/from_system_log_event classmethods,
    not in direct construction), and `severity` never changes based on what
    `severity_level` normalizes it to."""
    alert = UniFiAlert(
        category="security",
        message="test message",
        received_at=datetime.now(UTC),
        severity=raw,
    )

    assert alert.severity == raw
    # severity_level is derived independently and must never mutate severity.
    assert alert.severity == raw
    assert alert.severity_level in SEVERITY_ORDER
