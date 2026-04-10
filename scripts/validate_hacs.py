#!/usr/bin/env python3
"""Lightweight HACS integration validator.

Replicates the manifest and hacs.json checks that the HACS action performs
in CI, so failures are caught locally before push.

Usage:
    python scripts/validate_hacs.py

Exit code 0 = all checks passed. Non-zero = failures printed to stdout.

Keep HA_CORE_INTEGRATIONS in sync with:
    https://github.com/home-assistant/core/tree/dev/homeassistant/components
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# HA core built-in integrations. HACS rejects these in `dependencies` because
# they ship with HA and cannot be installed separately. Add entries here
# whenever the HACS action rejects a new one.
HA_CORE_INTEGRATIONS: frozenset[str] = frozenset(
    {
        "auth",
        "automation",
        "cloud",
        "config",
        "configurator",
        "conversation",
        "default_config",
        "dhcp",
        "energy",
        "frontend",
        "hassio",
        "history",
        "homeassistant",
        "http",
        "input_boolean",
        "input_button",
        "input_datetime",
        "input_number",
        "input_select",
        "input_text",
        "logbook",
        "lovelace",
        "map",
        "media_source",
        "mobile_app",
        "my",
        "network",
        "onboarding",
        "persistent_notification",
        "recorder",
        "repairs",
        "safe_mode",
        "script",
        "scene",
        "shopping_list",
        "ssdp",
        "sun",
        "system_health",
        "system_log",
        "tag",
        "timer",
        "trace",
        "usb",
        "webhook",
        "websocket_api",
        "zeroconf",
        "zone",
    }
)

MANIFEST_REQUIRED = {"domain", "name", "codeowners", "documentation", "iot_class", "version"}
VALID_IOT_CLASSES = {
    "assumed_state",
    "calculated",
    "cloud_polling",
    "cloud_push",
    "local_polling",
    "local_push",
}
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

HACS_VALID_KEYS = {"name", "content_in_root", "zip_release", "filename", "render_readme", "homeassistant"}


def validate_manifest(root: Path) -> list[str]:
    errors: list[str] = []
    path = root / "custom_components" / "unifi_alerts" / "manifest.json"
    try:
        manifest: dict = json.loads(path.read_text())
    except (json.JSONDecodeError, FileNotFoundError) as exc:
        return [f"manifest.json: {exc}"]

    for field in MANIFEST_REQUIRED:
        if field not in manifest:
            errors.append(f"manifest.json: missing required field '{field}'")

    version = manifest.get("version", "")
    if version and not VERSION_RE.match(version):
        errors.append(f"manifest.json: version '{version}' must be MAJOR.MINOR.PATCH")

    iot_class = manifest.get("iot_class", "")
    if iot_class and iot_class not in VALID_IOT_CLASSES:
        errors.append(f"manifest.json: unknown iot_class '{iot_class}'")

    for dep in manifest.get("dependencies", []):
        if dep in HA_CORE_INTEGRATIONS:
            errors.append(
                f"manifest.json: 'dependencies' contains HA core built-in '{dep}'. "
                "HACS rejects core integrations here — remove it."
            )

    return errors


def validate_hacs_json(root: Path) -> list[str]:
    errors: list[str] = []
    path = root / "hacs.json"
    try:
        hacs: dict = json.loads(path.read_text())
    except (json.JSONDecodeError, FileNotFoundError) as exc:
        return [f"hacs.json: {exc}"]

    if "name" not in hacs:
        errors.append("hacs.json: missing required field 'name'")

    if hacs.get("zip_release") and "filename" not in hacs:
        errors.append("hacs.json: zip_release is true but 'filename' is missing")

    for key in hacs:
        if key not in HACS_VALID_KEYS:
            errors.append(f"hacs.json: unknown key '{key}'")

    return errors


def main() -> int:
    root = Path(__file__).parent.parent
    errors = validate_manifest(root) + validate_hacs_json(root)

    if errors:
        print("HACS validation FAILED:")
        for err in errors:
            print(f"  FAIL  {err}")
        return 1

    print("HACS validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
