"""Tests for the UniFi authentication seam (UniFiAuth).

API-key auth only (#279): username/password login and method auto-detection
were removed, so UniFiAuth verifies the configured key and builds the
X-API-Key header, with no session state.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest

from custom_components.unifi_alerts.unifi_auth import (
    CannotConnectError,
    InvalidAuthError,
    SslCertificateError,
    UniFiAuth,
)


def make_auth(config: dict | None = None) -> UniFiAuth:
    """Create a standalone UniFiAuth for unit-testing auth logic in isolation."""
    session = MagicMock()
    cfg = config or {
        "api_key": "test-key",
        "verify_ssl": False,
    }
    return UniFiAuth(session, "https://192.168.1.1", cfg)


def _make_response(status: int, headers: dict | None = None):
    """Build a minimal mock aiohttp response for use in async context managers."""
    resp = MagicMock()
    resp.status = status
    resp.headers = headers or {}
    resp.raise_for_status = MagicMock()

    @asynccontextmanager
    async def _ctx(*args, **kwargs):
        yield resp

    return _ctx


class TestHeaders:
    """Tests for UniFiAuth.headers() — header construction in isolation."""

    def test_headers_always_include_api_key(self):
        auth = make_auth({"api_key": "test-key-123", "verify_ssl": False})
        headers = auth.headers()
        assert headers["X-API-Key"] == "test-key-123"
        assert headers["Accept"] == "application/json"

    def test_headers_empty_api_key_when_missing(self):
        auth = make_auth({"verify_ssl": False})
        headers = auth.headers()
        assert headers["X-API-Key"] == ""


class TestVerifyApiKey:
    """Tests for UniFiAuth._verify_api_key - tested in isolation via make_auth()."""

    @pytest.mark.asyncio
    async def test_missing_api_key_raises_invalid_auth(self):
        """No API key configured must raise InvalidAuthError before any request."""
        auth = make_auth({"verify_ssl": False})
        with pytest.raises(InvalidAuthError, match="No API key provided"):
            await auth._verify_api_key()

    @pytest.mark.asyncio
    async def test_always_uses_proxy_network_prefix(self):
        """_verify_api_key must always use /proxy/network prefix."""
        auth = make_auth({"api_key": "my-key", "verify_ssl": False})

        captured_url: list[str] = []

        @asynccontextmanager
        async def _ctx(*args, **kwargs):
            captured_url.append(args[0] if args else "")
            resp = MagicMock()
            resp.status = 200
            resp.headers = {}
            resp.raise_for_status = MagicMock()
            yield resp

        auth._session.get = _ctx
        await auth._verify_api_key()

        assert captured_url, "Expected at least one GET call"
        assert "/proxy/network" in captured_url[0], (
            f"Expected /proxy/network in URL, got: {captured_url[0]}"
        )

    @pytest.mark.asyncio
    async def test_404_raises_cannot_connect(self):
        """HTTP 404 from the API key endpoint must raise CannotConnectError, not bubble up."""
        auth = make_auth({"api_key": "my-key", "verify_ssl": False})
        ctx = _make_response(404)
        auth._session.get = ctx

        with pytest.raises(CannotConnectError, match="API key endpoint not found"):
            await auth._verify_api_key()

    @pytest.mark.asyncio
    async def test_401_raises_invalid_auth(self):
        """HTTP 401 from the API key endpoint must raise InvalidAuthError."""
        auth = make_auth({"api_key": "bad-key", "verify_ssl": False})
        ctx = _make_response(401)
        auth._session.get = ctx

        with pytest.raises(InvalidAuthError):
            await auth._verify_api_key()

    @pytest.mark.asyncio
    async def test_403_raises_invalid_auth(self):
        """HTTP 403 from the API key endpoint must raise InvalidAuthError."""
        auth = make_auth({"api_key": "bad-key", "verify_ssl": False})
        ctx = _make_response(403)
        auth._session.get = ctx

        with pytest.raises(InvalidAuthError):
            await auth._verify_api_key()

    @pytest.mark.asyncio
    async def test_invalid_auth_error_carries_login_url(self):
        """InvalidAuthError raised on 401 must carry the verify endpoint as login_url."""
        auth = make_auth({"api_key": "bad-key", "verify_ssl": False})
        ctx = _make_response(401)
        auth._session.get = ctx
        with pytest.raises(InvalidAuthError) as exc_info:
            await auth._verify_api_key()
        assert exc_info.value.login_url.endswith("/api/s/default/self")

    @pytest.mark.asyncio
    async def test_redirect_raises_cannot_connect(self):
        """A 3xx from the API key endpoint must raise CannotConnectError (no redirect)."""
        auth = make_auth({"api_key": "my-key", "verify_ssl": False})
        ctx = _make_response(302)
        auth._session.get = ctx

        with pytest.raises(CannotConnectError, match="redirect"):
            await auth._verify_api_key()

    @pytest.mark.asyncio
    async def test_verify_api_key_raises_ssl_cert_error(self):
        """aiohttp.ClientConnectorCertificateError in _verify_api_key must raise SslCertificateError."""
        import aiohttp

        auth = make_auth({"api_key": "test-key", "verify_ssl": True})

        @asynccontextmanager
        async def _raise(*args, **kwargs):
            raise aiohttp.ClientConnectorCertificateError(MagicMock(), MagicMock())
            yield  # type: ignore[misc]

        auth._session.get = _raise
        with pytest.raises(SslCertificateError):
            await auth._verify_api_key()

    @pytest.mark.asyncio
    async def test_verify_api_key_generic_client_error_raises_cannot_connect(self):
        """A generic aiohttp.ClientError in _verify_api_key must raise CannotConnectError.

        The message must be the exception class name, not str(err), so a URL that
        might embed the key is never surfaced.
        """
        import aiohttp

        auth = make_auth({"api_key": "test-key", "verify_ssl": True})

        @asynccontextmanager
        async def _raise(*args, **kwargs):
            raise aiohttp.ClientConnectionError("https://10.0.0.1/proxy/network?api_key=leaked")
            yield  # type: ignore[misc]

        auth._session.get = _raise
        with pytest.raises(CannotConnectError) as exc_info:
            await auth._verify_api_key()
        assert "leaked" not in str(exc_info.value)
        assert exc_info.value.args[0] == "ClientConnectionError"


class TestAuthenticate:
    """Tests for UniFiAuth.authenticate — API-key verification.

    Exercised at the HTTP layer (mocked session responses), not by
    monkeypatching _verify_api_key, so these fail if the real request/response
    handling breaks.
    """

    @pytest.mark.asyncio
    async def test_valid_key_authenticates(self):
        auth = make_auth({"api_key": "my-key", "verify_ssl": False})
        auth._session.get = _make_response(200)

        # Verification succeeds and returns nothing.
        assert await auth.authenticate() is None

    @pytest.mark.asyncio
    async def test_invalid_key_raises_invalid_auth(self):
        auth = make_auth({"api_key": "bad-key", "verify_ssl": False})
        auth._session.get = _make_response(401)

        with pytest.raises(InvalidAuthError):
            await auth.authenticate()

    @pytest.mark.asyncio
    async def test_missing_key_raises_invalid_auth(self):
        auth = make_auth({"verify_ssl": False})

        with pytest.raises(InvalidAuthError, match="No API key provided"):
            await auth.authenticate()


class TestSslCertificateError:
    """SslCertificateError is raised on TLS certificate failures, not CannotConnectError."""

    def test_ssl_cert_error_is_subclass_of_cannot_connect(self):
        assert issubclass(SslCertificateError, CannotConnectError)
