"""Severity normalisation and minimum-severity gating for the integration.

Maps a raw, ingestion-path-specific severity string onto one of four ordered
Severity_Level values, and provides the comparison helpers used by the
per-category Minimum_Severity_Setting gate. See docs/UNIFI.md for the
documented severity ordering.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Final, Literal, cast

from .const import CONF_MIN_SEVERITY

_LOGGER = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Severity_Level (an alert's own normalised severity)
# ──────────────────────────────────────────────
SEVERITY_LOW: Final = "LOW"
SEVERITY_MEDIUM: Final = "MEDIUM"
SEVERITY_HIGH: Final = "HIGH"
SEVERITY_VERY_HIGH: Final = "VERY_HIGH"

SeverityLevel = Literal["LOW", "MEDIUM", "HIGH", "VERY_HIGH"]

SEVERITY_ORDER: Final[list[SeverityLevel]] = [
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    SEVERITY_HIGH,
    SEVERITY_VERY_HIGH,
]

# Excluded from SEVERITY_ORDER so it can never be index()ed against a
# Minimum_Severity_Setting; meets_minimum() fails open for it instead, since
# conflating "unknown" with LOW would silently mute alerts whose severity
# could not be determined (e.g. webhook/legacy payloads with no severity
# field).
SEVERITY_UNKNOWN: Final = "UNKNOWN"

# ──────────────────────────────────────────────
# Minimum_Severity_Setting (a category's configured gate threshold)
# ──────────────────────────────────────────────
# Lowercase (unlike the SEVERITY_* values) so it can never be confused with an
# alert's own normalised severity. The backward-compatible default: a stored
# LOW default would silently start gating every existing installation the
# moment this feature shipped, whereas No_Filter preserves prior behaviour
# until a user opts in.
MIN_SEVERITY_NO_FILTER: Final = "no_filter"

MinimumSeverity = Literal["UNKNOWN", "no_filter", "LOW", "MEDIUM", "HIGH", "VERY_HIGH"]

# Selector ordering only: No_Filter sits below LOW for UI purposes but is not
# itself a Severity_Level and is never returned by normalize_severity().
MIN_SEVERITY_ORDER: Final[list[MinimumSeverity]] = [MIN_SEVERITY_NO_FILTER, *SEVERITY_ORDER]

# ──────────────────────────────────────────────
# Normalisation
# ──────────────────────────────────────────────
_CANONICAL_LOOKUP: Final[dict[str, SeverityLevel]] = {
    level.lower(): level for level in SEVERITY_ORDER
}


def normalize_severity(raw: str) -> MinimumSeverity:
    """Map a raw severity string to one of SEVERITY_ORDER, or SEVERITY_UNKNOWN.

    Matches case-insensitively, ignoring leading/trailing whitespace, against
    the canonical Severity_Level names. Anything else (including an empty
    string, or the webhook/legacy `subsystem` fallback e.g. "wlan") maps to
    SEVERITY_UNKNOWN.
    """
    key = raw.strip().lower()
    if key in _CANONICAL_LOOKUP:
        return _CANONICAL_LOOKUP[key]
    return SEVERITY_UNKNOWN


def meets_minimum(severity_level: MinimumSeverity, minimum: MinimumSeverity) -> bool:
    """Return True if severity_level satisfies minimum.

    Fails open (returns True) for MIN_SEVERITY_NO_FILTER and for
    SEVERITY_UNKNOWN; otherwise compares SEVERITY_ORDER positions.
    """
    if minimum == MIN_SEVERITY_NO_FILTER or severity_level == SEVERITY_UNKNOWN:
        return True
    # The guard above only excludes each sentinel from the variable it was
    # checked against, not from MinimumSeverity as a whole - cast narrows
    # both to SeverityLevel for the index() lookup.
    severity_index = SEVERITY_ORDER.index(cast(SeverityLevel, severity_level))
    minimum_index = SEVERITY_ORDER.index(cast(SeverityLevel, minimum))
    return severity_index >= minimum_index


def get_effective_min_severity(config: Mapping[str, Any], category: str) -> MinimumSeverity:
    """Resolve the effective Minimum_Severity_Setting for a category.

    Centralised so the "missing means No_Filter" default (map absent, or
    category key absent from it) can never drift between the push and poll
    call sites. A stored value outside MIN_SEVERITY_ORDER - only reachable via
    a hand-edited config entry, since the SelectSelector validates in-band
    submissions - is coerced to MIN_SEVERITY_NO_FILTER and logged, rather than
    later raising ValueError out of meets_minimum's index() lookup.
    """
    raw: Any = config.get(CONF_MIN_SEVERITY, {})
    min_severity_map: Mapping[str, str] = raw if isinstance(raw, Mapping) else {}
    resolved: str = min_severity_map.get(category, MIN_SEVERITY_NO_FILTER)
    if resolved not in MIN_SEVERITY_ORDER:
        _LOGGER.warning(
            "Ignoring unrecognised min_severity %r for category %r; treating as %s",
            resolved,
            category,
            MIN_SEVERITY_NO_FILTER,
        )
        return MIN_SEVERITY_NO_FILTER
    return resolved
