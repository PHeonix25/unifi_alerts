"""Authentication seam for the UniFi Network controller.

Holds the exceptions and the UniFiAuth class that UniFiClient composes for all
credential verification, session state, and header construction. Kept in its
own module so auth logic is unit-testable independently of transport,
pagination, or alarm parsing.
"""

from __future__ import annotations

import logging

import aiohttp

from .const import (
    AUTH_METHOD_APIKEY,
    AUTH_METHOD_USERPASS,
    CONF_API_KEY,
    CONF_AUTH_METHOD,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    DEFAULT_VERIFY_SSL,
)
from .models import UniFiClientConfig

_LOGGER = logging.getLogger(__name__)

# UniFi OS consoles (UDM, UCG, etc.) prefix all network API paths
UNIFI_OS_NETWORK_PREFIX = "/proxy/network"


class CannotConnectError(Exception):
    """Raised when the controller is unreachable."""


class SslCertificateError(CannotConnectError):
    """Raised when TLS certificate verification fails.

    Subclass of CannotConnectError so coordinator/integration code that only
    catches CannotConnectError continues to work. The config flow catches this
    subclass first to surface a dedicated, actionable error message.
    """


class InvalidAuthError(Exception):
    """Raised on 401/403 responses.

    Attributes:
        login_url: The URL that returned the auth failure; surfaced in the UI.
    """

    def __init__(self, message: str, *, login_url: str = "") -> None:
        super().__init__(message)
        self.login_url = login_url


class UniFiAuth:
    """Authentication seam for UniFi OS controllers.

    Handles auth-method auto-detection, credential verification, session state,
    and header construction.

    Supports:
      - API key auth (X-API-Key header)
      - Username/password auth (session cookie)
      - Auto-detection: tries API key first, falls back to username/password
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        config: UniFiClientConfig,
    ) -> None:
        self._session = session
        self._base = base_url
        self._config = config
        self._method: str | None = None
        self._authenticated: bool = False

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    @property
    def method(self) -> str | None:
        return self._method

    def invalidate(self) -> None:
        """Mark the current session as expired (call on 401 responses)."""
        self._authenticated = False

    def headers(self) -> dict[str, str]:
        """Return HTTP headers for an authenticated request."""
        hdrs: dict[str, str] = {"Accept": "application/json"}
        if self._method == AUTH_METHOD_APIKEY:
            hdrs["X-API-Key"] = self._config.get(CONF_API_KEY, "")
        return hdrs

    async def authenticate(self) -> str:
        """Authenticate to the UniFi OS controller. Returns the auth method used."""
        method = self._config.get(CONF_AUTH_METHOD)

        if method == AUTH_METHOD_APIKEY or (method is None and self._config.get(CONF_API_KEY)):
            try:
                await self._verify_api_key()
                self._method = AUTH_METHOD_APIKEY
                self._authenticated = True
                _LOGGER.debug("Authenticated via API key")
                return AUTH_METHOD_APIKEY
            except InvalidAuthError:
                if method == AUTH_METHOD_APIKEY:
                    raise
                _LOGGER.debug("API key failed, falling back to username/password")

        await self._login_userpass()
        self._method = AUTH_METHOD_USERPASS
        self._authenticated = True
        _LOGGER.debug("Authenticated via username/password")
        return AUTH_METHOD_USERPASS

    async def _verify_api_key(self) -> None:
        api_key = self._config.get(CONF_API_KEY, "")
        if not api_key:
            raise InvalidAuthError("No API key provided")
        endpoint = f"{self._base}{UNIFI_OS_NETWORK_PREFIX}/api/s/default/self"
        try:
            async with self._session.get(
                endpoint,
                headers={"X-API-Key": api_key, "Accept": "application/json"},
                ssl=self._config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
                timeout=aiohttp.ClientTimeout(total=8),
                allow_redirects=False,
            ) as resp:
                if 300 <= resp.status < 400:
                    raise CannotConnectError(
                        f"Controller issued a redirect (HTTP {resp.status}) on an authenticated "
                        "request; refusing to follow to protect credentials"
                    )
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
        # fmt: skip below: the pinned ruff formatter (0.15.x, target py314)
        # incorrectly strips the parentheses from a multi-type except clause,
        # producing invalid Python. The guard keeps the required parens.
        except (CannotConnectError, InvalidAuthError):  # fmt: skip
            raise
        except aiohttp.ClientConnectorCertificateError as err:
            raise SslCertificateError(type(err).__name__) from err
        except aiohttp.ClientError as err:
            raise CannotConnectError(type(err).__name__) from err

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
                    allow_redirects=False,
                ) as resp:
                    if 300 <= resp.status < 400:
                        raise CannotConnectError(
                            f"Controller login endpoint issued a redirect (HTTP {resp.status}); "
                            "check the controller URL"
                        )
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
            last_url = paths[-1]
            _LOGGER.warning("Authentication failed at login path (last: %s)", last_url)
            raise InvalidAuthError("Invalid username or password", login_url=last_url)
        except aiohttp.ClientConnectorCertificateError as err:
            raise SslCertificateError(type(err).__name__) from err
        except aiohttp.ClientResponseError as err:
            raise CannotConnectError(f"{type(err).__name__} {err.status}") from err
        except aiohttp.ClientError as err:
            raise CannotConnectError(type(err).__name__) from err
