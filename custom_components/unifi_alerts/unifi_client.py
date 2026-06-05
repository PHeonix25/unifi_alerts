"""Async HTTP client for the UniFi Network controller."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp

from .const import (
    AUTH_METHOD_APIKEY,
    AUTH_METHOD_USERPASS,
    CONF_API_KEY,
    CONF_AUTH_METHOD,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    DEFAULT_SYSTEM_LOG_LOOKBACK_HOURS,
    DEFAULT_VERIFY_SSL,
    MAX_SYSTEM_LOG_PAGES,
    SYSTEM_LOG_PAGE_SIZE,
    UNIFI_KEY_TO_CATEGORY,
)
from .models import UniFiAlert, UniFiClientConfig

_LOGGER = logging.getLogger(__name__)

# UniFi OS consoles (UDM, UCG, etc.) prefix all network API paths
UNIFI_OS_NETWORK_PREFIX = "/proxy/network"

# After this many consecutive transient probe failures, stop re-probing and
# fall back to the legacy path. A single network blip should not pin the
# client to legacy mode, so the threshold is intentionally > 1.
_PROBE_FAIL_LIMIT = 5
# How long to wait before attempting another probe after the threshold is hit.
_PROBE_RETRY_AFTER = timedelta(hours=1)


class CannotConnectError(Exception):
    """Raised when the controller is unreachable."""


class InvalidAuthError(Exception):
    """Raised on 401/403 responses.

    Attributes:
        login_url: The URL that returned the auth failure; surfaced in the UI.
    """

    def __init__(self, message: str, *, login_url: str = "") -> None:
        super().__init__(message)
        self.login_url = login_url


class UniFiClient:
    """Minimal async client for fetching alarms from a UniFi controller.

    Supports:
      - Username/password auth (session cookie)
      - API key auth (X-API-Key header)
      - Auto-detection: tries API key first, falls back to user/pass

    Requires UniFi OS (UDM, UDM-Pro, UDM-SE, UCG-Ultra, UCG-Max, Cloud Key Gen2+).
    Classic self-hosted Network Application controllers are not supported.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        controller_url: str,
        config: UniFiClientConfig,
    ) -> None:
        self._session = session
        self._base = controller_url.rstrip("/")
        self._config: UniFiClientConfig = config
        self._auth_method: str | None = None
        self._authenticated: bool = False
        # None = not yet probed. authenticate() detects v2 system-log availability
        # on first connect; fetch_alarms() falls back to legacy /list/alarm if False.
        self._has_system_log: bool | None = None
        # Consecutive transient probe failures. Resets to 0 on any definitive result.
        self._probe_fail_count: int = 0
        # Set when _probe_fail_count reaches _PROBE_FAIL_LIMIT; clears on retry window expiry.
        self._probe_backoff_until: datetime | None = None

    # ── Public interface ──────────────────────────────────────────────────

    async def authenticate(self) -> str:
        """Authenticate to the UniFi OS controller. Returns the auth method used."""
        method = self._config.get(CONF_AUTH_METHOD)

        if method == AUTH_METHOD_APIKEY or (method is None and self._config.get(CONF_API_KEY)):
            try:
                await self._verify_api_key()
                self._auth_method = AUTH_METHOD_APIKEY
                self._authenticated = True
                _LOGGER.debug("Authenticated via API key")
                return AUTH_METHOD_APIKEY
            except InvalidAuthError:
                if method == AUTH_METHOD_APIKEY:
                    raise
                _LOGGER.debug("API key failed, falling back to username/password")

        # Username / password
        await self._login_userpass()
        self._auth_method = AUTH_METHOD_USERPASS
        self._authenticated = True
        _LOGGER.debug("Authenticated via username/password")
        return AUTH_METHOD_USERPASS

    async def fetch_alarms(self, site: str = "default") -> list[dict[str, Any]]:
        """Return all unarchived alarms from the controller."""
        if not self._authenticated:
            await self.authenticate()

        # Different firmware versions expose the alarm endpoint at different paths.
        # Try the newest path first so modern firmware succeeds in one call; fall
        # back to older variants for backwards compatibility. Order matters —
        # update docs/UNIFI.md § "Alarm API endpoint" if you change this list.
        #
        #   /list/alarm  — newest (UniFi Network 9.x+)
        #   /alarm       — long-standing universal path
        #   /stat/alarm  — older intermediate variant; some firmware exposes only this
        alarm_paths = [
            f"{self._base}{UNIFI_OS_NETWORK_PREFIX}/api/s/{site}/list/alarm",
            f"{self._base}{UNIFI_OS_NETWORK_PREFIX}/api/s/{site}/alarm",
            f"{self._base}{UNIFI_OS_NETWORK_PREFIX}/api/s/{site}/stat/alarm",
        ]
        for path in alarm_paths:
            result = await self._try_fetch_alarms(path, site)
            if result is not None:
                return result
            # None means path not found (404 or api.err.InvalidObject) — try next
        raise CannotConnectError(
            f"Could not find the alarm endpoint for site '{site}'. Tried: {', '.join(alarm_paths)}"
        )

    async def _try_fetch_alarms(self, url: str, site: str) -> list[dict[str, Any]] | None:
        """Fetch alarms from one URL. Returns None on 404 (caller tries next URL)."""
        _LOGGER.debug("Fetching alarms from %s", url)
        try:
            async with self._session.get(
                url,
                headers=self._headers(),
                ssl=self._config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 401:
                    self._authenticated = False
                    raise InvalidAuthError("Session expired")
                if resp.status == 404:
                    _LOGGER.debug("Alarm URL %s returned 404 — trying next URL", url)
                    return None
                if resp.status == 400:
                    # UniFi returns JSON even on 400 — parse the msg field.
                    # Some firmware returns 400 + api.err.InvalidObject for paths that
                    # don't exist on that firmware version (instead of 404), so treat
                    # that error code as "path not found" and let the caller try the
                    # next path. Any other 400 is a genuine error worth surfacing.
                    unifi_msg = ""
                    try:
                        body = await resp.json(content_type=None)
                        unifi_msg = body.get("meta", {}).get("msg", "")
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.debug(
                            "Could not parse 400 response body from %s: %s",
                            url,
                            type(err).__name__,
                        )
                    if unifi_msg == "api.err.InvalidObject":
                        _LOGGER.debug(
                            "Alarm URL %s returned 400 api.err.InvalidObject — trying next URL",
                            url,
                        )
                        return None
                    detail = f" ({unifi_msg})" if unifi_msg else ""
                    raise CannotConnectError(
                        f"Alarm endpoint rejected the request (HTTP 400{detail}). "
                        f"Check that the site name '{site}' exists on the controller."
                    )
                resp.raise_for_status()
                data = await resp.json()
                if data.get("meta", {}).get("rc") != "ok":
                    msg = data.get("meta", {}).get("msg", "unknown error")
                    raise CannotConnectError(f"UniFi API error: {msg}")
                return [a for a in data.get("data", []) if not a.get("archived", False)]
        except aiohttp.ClientResponseError as err:
            # Include HTTP status so users (and logs) can tell a 404 from a 500.
            # Status-only — no URL — to avoid leaking creds that may be embedded in a URL.
            raise CannotConnectError(f"{type(err).__name__} {err.status}") from err
        except aiohttp.ClientError as err:
            raise CannotConnectError(type(err).__name__) from err

    async def probe_system_log_endpoint(self, site: str = "default") -> bool:
        """Probe the v2 system-log endpoint to determine whether it is available.

        Calls POST /proxy/network/v2/api/site/{site}/system-log/count with an
        empty body. A 200 response indicates availability; 404 is the
        controller's definitive "endpoint not implemented" response. Any other
        4xx/5xx or network error is treated as transient.

        Cache semantics:
        - 200 sets _has_system_log=True (permanent until re-auth).
        - 404 sets _has_system_log=False with no retry (_probe_backoff_until=None).
        - A single transient failure leaves _has_system_log=None (re-probes next poll).
        - After _PROBE_FAIL_LIMIT consecutive transient failures, _has_system_log is
          set to False and _probe_backoff_until is set to now + _PROBE_RETRY_AFTER.
          Once that window expires the probe resets to None and retries.
        """
        if self._has_system_log is not None:
            # For a backoff-triggered False, check whether the retry window has opened.
            if self._has_system_log is False and self._probe_backoff_until is not None:
                if datetime.now(UTC) >= self._probe_backoff_until:
                    _LOGGER.debug("v2 system-log probe backoff expired; will retry")
                    self._has_system_log = None
                    self._probe_fail_count = 0
                    self._probe_backoff_until = None
                    # Fall through to probe below.
                else:
                    return False
            else:
                return self._has_system_log

        if not self._authenticated:
            await self.authenticate()

        url = f"{self._base}{UNIFI_OS_NETWORK_PREFIX}/v2/api/site/{site}/system-log/count"
        _LOGGER.debug("Probing v2 system-log endpoint: %s", url)
        try:
            async with self._session.post(
                url,
                json={},
                headers=self._headers(),
                ssl=self._config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    _LOGGER.debug("v2 system-log endpoint available")
                    self._has_system_log = True
                    self._probe_fail_count = 0
                    self._probe_backoff_until = None
                    return True
                if resp.status == 404:
                    _LOGGER.debug(
                        "v2 system-log endpoint not implemented (HTTP 404); using legacy path"
                    )
                    self._has_system_log = False
                    self._probe_fail_count = 0
                    return False
                self._probe_fail_count += 1
                if self._probe_fail_count >= _PROBE_FAIL_LIMIT:
                    self._has_system_log = False
                    self._probe_backoff_until = datetime.now(UTC) + _PROBE_RETRY_AFTER
                    _LOGGER.debug(
                        "v2 system-log probe failed %d consecutive times (HTTP %d); "
                        "switching to legacy path for %s",
                        _PROBE_FAIL_LIMIT,
                        resp.status,
                        _PROBE_RETRY_AFTER,
                    )
                else:
                    _LOGGER.debug(
                        "v2 system-log probe got HTTP %d (transient, %d/%d); "
                        "legacy path this poll, will retry next",
                        resp.status,
                        self._probe_fail_count,
                        _PROBE_FAIL_LIMIT,
                    )
                return False
        except aiohttp.ClientError as err:
            self._probe_fail_count += 1
            if self._probe_fail_count >= _PROBE_FAIL_LIMIT:
                self._has_system_log = False
                self._probe_backoff_until = datetime.now(UTC) + _PROBE_RETRY_AFTER
                _LOGGER.debug(
                    "v2 system-log probe failed %d consecutive times (%s); "
                    "switching to legacy path for %s",
                    _PROBE_FAIL_LIMIT,
                    type(err).__name__,
                    _PROBE_RETRY_AFTER,
                )
            else:
                _LOGGER.debug(
                    "v2 system-log probe failed with %s (transient, %d/%d); "
                    "legacy path this poll, will retry next",
                    type(err).__name__,
                    self._probe_fail_count,
                    _PROBE_FAIL_LIMIT,
                )
            return False

    async def fetch_system_log_alarms(
        self,
        site: str = "default",
        since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch alarms from the v2 system-log/all endpoint with pagination.

        Uses timestampFrom = since (or now - DEFAULT_SYSTEM_LOG_LOOKBACK_HOURS
        when not specified) and paginates through results up to
        MAX_SYSTEM_LOG_PAGES pages. Returns the raw alarm dicts as-is for the
        caller to parse with UniFiAlert.from_system_log_event().

        Only events with status="NEW" are returned (equivalent to the legacy
        archived=False filter). Events with any other status are skipped.
        """
        if not self._authenticated:
            await self.authenticate()

        now = datetime.now(UTC)
        if since is not None:
            from_dt = since
        else:
            from_dt = now - timedelta(hours=DEFAULT_SYSTEM_LOG_LOOKBACK_HOURS)

        timestamp_from = int(from_dt.timestamp() * 1000)
        timestamp_to = int(now.timestamp() * 1000)

        url = f"{self._base}{UNIFI_OS_NETWORK_PREFIX}/v2/api/site/{site}/system-log/all"
        results: list[dict[str, Any]] = []

        for page in range(MAX_SYSTEM_LOG_PAGES):
            body = {
                "timestampFrom": timestamp_from,
                "timestampTo": timestamp_to,
                "pageNumber": page,
                "pageSize": SYSTEM_LOG_PAGE_SIZE,
            }
            _LOGGER.debug(
                "Fetching v2 system-log page %d from %s",
                page,
                url,
            )
            try:
                async with self._session.post(
                    url,
                    json=body,
                    headers=self._headers(),
                    ssl=self._config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 401:
                        self._authenticated = False
                        raise InvalidAuthError("Session expired during system-log fetch")
                    resp.raise_for_status()
                    data = await resp.json()
            except aiohttp.ClientResponseError as err:
                raise CannotConnectError(f"{type(err).__name__} {err.status}") from err
            except aiohttp.ClientError as err:
                raise CannotConnectError(type(err).__name__) from err

            page_data: list[dict[str, Any]] = data.get("data") or []
            # Filter to open/unacknowledged events only (status="NEW")
            new_events = [e for e in page_data if e.get("status") == "NEW"]
            results.extend(new_events)

            total_pages: int = data.get("total_page_count", 1)
            _LOGGER.debug(
                "v2 system-log page %d: %d total events, %d NEW, %d/%d pages",
                page,
                len(page_data),
                len(new_events),
                page + 1,
                total_pages,
            )
            if page + 1 >= total_pages or not page_data:
                break

        return results

    async def categorise_alarms(self, site: str = "default") -> dict[str, list[UniFiAlert]]:
        """Fetch alarms and group them by category."""
        raw = await self.fetch_alarms(site)
        result: dict[str, list[UniFiAlert]] = {}
        for alarm in raw:
            category = self._classify(alarm)
            if category is None:
                continue
            alert = UniFiAlert.from_api_alarm(category, alarm)
            result.setdefault(category, []).append(alert)
        return result

    async def close(self) -> None:
        if self._auth_method == AUTH_METHOD_USERPASS and self._authenticated:
            try:
                await self._session.post(
                    f"{self._base}/api/auth/logout",
                    ssl=self._config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
                    timeout=aiohttp.ClientTimeout(total=5),
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("UniFi logout failed: %s", type(err).__name__)

    # ── Private helpers ───────────────────────────────────────────────────

    async def _verify_api_key(self) -> None:
        api_key = self._config.get(CONF_API_KEY, "")
        if not api_key:
            raise InvalidAuthError("No API key provided")
        endpoint = f"{self._base}{UNIFI_OS_NETWORK_PREFIX}/api/s/default/self"
        async with self._session.get(
            endpoint,
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            ssl=self._config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status == 404:
                raise CannotConnectError(
                    "API key endpoint not found — check the controller URL "
                    "and that UniFi OS is accessible at this address"
                )
            if resp.status in (401, 403):
                _LOGGER.warning(
                    "API key authentication failed for %s (HTTP %d)", endpoint, resp.status
                )
                raise InvalidAuthError("Invalid API key", login_url=endpoint)
            resp.raise_for_status()

    async def _login_userpass(self) -> None:
        """Attempt username/password login via the UniFi OS path."""
        paths = [f"{self._base}/api/auth/login"]

        payload = {
            "username": self._config.get(CONF_USERNAME, ""),
            "password": self._config.get(CONF_PASSWORD, ""),
        }
        try:
            for login_url in paths:
                async with self._session.post(
                    login_url,
                    json=payload,
                    ssl=self._config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 400:
                        _LOGGER.warning(
                            "Controller rejected login request at %s (HTTP 400). "
                            "Check the controller URL and that the controller version "
                            "supports this integration.",
                            login_url,
                        )
                        raise CannotConnectError(
                            "Controller rejected login request (HTTP 400). "
                            "Check the controller URL and that the controller version "
                            "supports this integration."
                        )
                    if resp.status in (401, 403):
                        _LOGGER.debug(
                            "Authentication failed at %s (HTTP %d)",
                            login_url,
                            resp.status,
                        )
                        continue
                    resp.raise_for_status()
                    return  # success
            # Path returned 401/403
            last_url = paths[-1]
            _LOGGER.warning("Authentication failed at login path (last: %s)", last_url)
            raise InvalidAuthError("Invalid username or password", login_url=last_url)
        except aiohttp.ClientResponseError as err:
            raise CannotConnectError(f"{type(err).__name__} {err.status}") from err
        except aiohttp.ClientError as err:
            raise CannotConnectError(type(err).__name__) from err

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._auth_method == AUTH_METHOD_APIKEY:
            headers["X-API-Key"] = self._config.get(CONF_API_KEY, "")
        return headers

    @staticmethod
    def _classify(alarm: dict[str, Any]) -> str | None:
        """Map a raw alarm dict to a category string, or None if unrecognised."""
        key = alarm.get("key", "")
        for prefix, category in UNIFI_KEY_TO_CATEGORY.items():
            if key.startswith(prefix):
                return category
        if key:
            _LOGGER.debug(
                "Unclassified UniFi event key %r — consider reporting it at "
                "https://github.com/PHeonix25/unifi_alerts/issues",
                key,
            )
        return None
