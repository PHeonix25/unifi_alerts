"""Async HTTP client for the UniFi Network controller."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import (
    AUTH_METHOD_APIKEY,
    AUTH_METHOD_USERPASS,
    CONF_API_KEY,
    CONF_AUTH_METHOD,
    CONF_IS_UNIFI_OS,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    UNIFI_KEY_TO_CATEGORY,
)
from .models import UniFiAlert

_LOGGER = logging.getLogger(__name__)

# UniFi OS consoles (UDM, UCG, etc.) prefix all network API paths
UNIFI_OS_NETWORK_PREFIX = "/proxy/network"


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
      - Username/password auth (session cookie) — all controller types
      - API key auth (X-API-Key header) — UniFi OS only
      - Auto-detection: tries API key first, falls back to user/pass
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        controller_url: str,
        config: dict[str, Any],
    ) -> None:
        self._session = session
        self._base = controller_url.rstrip("/")
        self._config = config
        self._is_unifi_os: bool | None = config.get(CONF_IS_UNIFI_OS)
        self._auth_method: str | None = None
        self._authenticated: bool = False

    # ── Public interface ──────────────────────────────────────────────────

    async def authenticate(self) -> str:
        """Detect controller type and authenticate. Returns the auth method used."""
        if self._is_unifi_os is None:
            self._is_unifi_os = await self._detect_unifi_os()

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

    async def fetch_alarms(self, site: str = "default") -> list[dict]:
        """Return all unarchived alarms from the controller."""
        if not self._authenticated:
            await self.authenticate()

        path = self._network_path(f"/api/s/{site}/alarm")
        try:
            async with self._session.get(
                f"{self._base}{path}",
                params={"limit": 200},
                headers=self._headers(),
                ssl=self._config.get(CONF_VERIFY_SSL, False),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 401:
                    self._authenticated = False
                    raise InvalidAuthError("Session expired")
                resp.raise_for_status()
                data = await resp.json()
                if data.get("meta", {}).get("rc") != "ok":
                    msg = data.get("meta", {}).get("msg", "unknown error")
                    raise CannotConnectError(f"UniFi API error: {msg}")
                return [a for a in data.get("data", []) if not a.get("archived", False)]
        except aiohttp.ClientError as err:
            raise CannotConnectError(str(err)) from err

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
                logout_path = "/api/logout" if not self._is_unifi_os else "/api/auth/logout"
                await self._session.post(
                    f"{self._base}{logout_path}",
                    ssl=self._config.get(CONF_VERIFY_SSL, False),
                    timeout=aiohttp.ClientTimeout(total=5),
                )
            except Exception:  # noqa: BLE001
                pass

    # ── Private helpers ───────────────────────────────────────────────────

    async def _detect_unifi_os(self) -> bool:
        """Return True if this is a UniFi OS console (UDM/UCG/etc.).

        Two-stage detection:
        1. Check for ``x-csrf-token`` in the ``/`` response (primary heuristic).
           Follows redirects so HTTP→HTTPS redirects (e.g. UCG-Ultra) are handled.
        2. If the token is absent, probe ``/api/system`` — a UniFi OS-only endpoint.
           Returns 200 on OS consoles, 404 on classic controllers.
        """
        ssl = self._config.get(CONF_VERIFY_SSL, False)
        timeout = aiohttp.ClientTimeout(total=5)
        try:
            async with self._session.get(
                f"{self._base}/",
                ssl=ssl,
                allow_redirects=True,
                timeout=timeout,
            ) as resp:
                if resp.headers.get("x-csrf-token") is not None:
                    _LOGGER.debug(
                        "UniFi OS detection: True via x-csrf-token (status %d)", resp.status
                    )
                    return True
        except Exception:  # noqa: BLE001
            return False

        # x-csrf-token absent — try the /api/system fallback probe
        try:
            async with self._session.get(
                f"{self._base}/api/system",
                ssl=ssl,
                allow_redirects=True,
                timeout=timeout,
            ) as probe:
                is_os = probe.status == 200
                _LOGGER.debug(
                    "UniFi OS detection (fallback /api/system probe): %s (status %d)",
                    is_os,
                    probe.status,
                )
                return is_os
        except Exception:  # noqa: BLE001
            return False

    async def _verify_api_key(self) -> None:
        api_key = self._config.get(CONF_API_KEY, "")
        if not api_key:
            raise InvalidAuthError("No API key provided")
        # API keys are UniFi OS-only, so always use the /proxy/network prefix regardless
        # of what _detect_unifi_os() returned.  Trusting the detection result here caused
        # 404 errors on UCG-Ultra and reverse-proxy setups where x-csrf-token is absent.
        endpoint = f"{self._base}{UNIFI_OS_NETWORK_PREFIX}/api/s/default/self"
        async with self._session.get(
            endpoint,
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            ssl=self._config.get(CONF_VERIFY_SSL, False),
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
        """Attempt username/password login, trying both UniFi OS and classic paths.

        UniFi OS detection via ``x-csrf-token`` can give a false negative for some
        UCG-Ultra firmware versions.  We therefore always try both endpoint paths:
        the detected-primary path first, then the alternate path as a fallback.
        """
        if self._is_unifi_os:
            paths = [f"{self._base}/api/auth/login", f"{self._base}/api/login"]
        else:
            paths = [f"{self._base}/api/login", f"{self._base}/api/auth/login"]

        payload = {
            "username": self._config.get(CONF_USERNAME, ""),
            "password": self._config.get(CONF_PASSWORD, ""),
        }
        try:
            for login_url in paths:
                async with self._session.post(
                    login_url,
                    json=payload,
                    ssl=self._config.get(CONF_VERIFY_SSL, False),
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
                            "Authentication failed at %s (HTTP %d) — trying alternate path",
                            login_url,
                            resp.status,
                        )
                        continue
                    resp.raise_for_status()
                    return  # success
            # Both paths returned 401/403
            last_url = paths[-1]
            _LOGGER.warning("Authentication failed at all login paths (last: %s)", last_url)
            raise InvalidAuthError("Invalid username or password", login_url=last_url)
        except aiohttp.ClientError as err:
            raise CannotConnectError(str(err)) from err

    def _network_path(self, path: str) -> str:
        """Prefix path with /proxy/network on UniFi OS controllers."""
        if self._is_unifi_os:
            return f"{UNIFI_OS_NETWORK_PREFIX}{path}"
        return path

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._auth_method == AUTH_METHOD_APIKEY:
            headers["X-API-Key"] = self._config.get(CONF_API_KEY, "")
        return headers

    @staticmethod
    def _classify(alarm: dict) -> str | None:
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
        # Fallback: check subsystem field
        subsystem = alarm.get("subsystem", "").lower()
        if subsystem in ("lan", "wlan"):
            return None  # too broad — skip unless key matched
        return None
