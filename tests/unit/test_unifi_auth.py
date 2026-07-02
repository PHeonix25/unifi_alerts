"""Tests for the UniFi authentication seam (UniFiAuth)."""

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
        "username": "admin",
        "password": "password",
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
    """Tests for UniFiAuth.headers() — auth header construction in isolation."""

    def test_userpass_auth_no_api_key_header(self):
        auth = make_auth()
        auth._method = "userpass"
        headers = auth.headers()
        assert "X-API-Key" not in headers

    def test_apikey_auth_adds_header(self):
        auth = make_auth({"api_key": "test-key-123", "verify_ssl": False})
        auth._method = "apikey"
        headers = auth.headers()
        assert headers.get("X-API-Key") == "test-key-123"


class TestLoginUserpass:
    """Tests for UniFiAuth._login_userpass - tested in isolation via make_auth()."""

    @pytest.mark.asyncio
    async def test_http_400_raises_cannot_connect(self):
        """HTTP 400 from the controller must raise CannotConnectError, not InvalidAuthError.

        UCG-Ultra returns 400 for request format / endpoint mismatch — this is
        NOT a credentials problem, so we must not show 'invalid credentials'.
        """
        auth = make_auth()
        ctx = _make_response(400)
        auth._session.post = ctx
        with pytest.raises(CannotConnectError):
            await auth._login_userpass()

    @pytest.mark.asyncio
    async def test_login_client_error_message_is_class_name_not_url(self):
        """CannotConnectError from _login_userpass must use class name, not str(err).

        Same credential-leak prevention as fetch_alarms: aiohttp errors can embed
        the login URL (which may contain the password) in their string representation.
        """
        import aiohttp

        auth = make_auth()

        @asynccontextmanager
        async def _raise(*args, **kwargs):
            raise aiohttp.ClientConnectionError("https://admin:hunter2@192.168.1.1/api/login")
            yield

        auth._session.post = _raise
        with pytest.raises(CannotConnectError) as exc_info:
            await auth._login_userpass()
        assert "hunter2" not in str(exc_info.value)
        assert exc_info.value.args[0] == "ClientConnectionError"

    @pytest.mark.asyncio
    async def test_http_401_raises_invalid_auth(self):
        """HTTP 401 should still raise InvalidAuthError (bad credentials)."""
        auth = make_auth()
        ctx = _make_response(401)
        auth._session.post = ctx
        with pytest.raises(InvalidAuthError):
            await auth._login_userpass()

    @pytest.mark.asyncio
    async def test_http_403_raises_invalid_auth(self):
        """HTTP 403 should still raise InvalidAuthError (bad credentials)."""
        auth = make_auth()
        ctx = _make_response(403)
        auth._session.post = ctx
        with pytest.raises(InvalidAuthError):
            await auth._login_userpass()

    @pytest.mark.asyncio
    async def test_invalid_auth_error_carries_login_url(self):
        """InvalidAuthError raised must carry login_url attribute pointing to /api/auth/login."""
        auth = make_auth()
        ctx = _make_response(401)
        auth._session.post = ctx
        with pytest.raises(InvalidAuthError) as exc_info:
            await auth._login_userpass()
        # UniFi OS path is the only path now.
        assert exc_info.value.login_url.endswith("/api/auth/login")

    @pytest.mark.asyncio
    async def test_success_returns_without_error(self):
        """HTTP 200 from the UniFi OS login path must succeed without raising."""
        auth = make_auth()
        ctx = _make_response(200)
        auth._session.post = ctx
        # Should not raise
        await auth._login_userpass()

    @pytest.mark.asyncio
    async def test_redirect_raises_cannot_connect(self):
        """3xx from the login endpoint must raise CannotConnectError, not follow the redirect."""
        auth = make_auth()
        ctx = _make_response(302)
        auth._session.post = ctx
        with pytest.raises(CannotConnectError, match="redirect"):
            await auth._login_userpass()

    @pytest.mark.asyncio
    async def test_login_userpass_raises_ssl_cert_error(self):
        """aiohttp.ClientConnectorCertificateError in _login_userpass must raise SslCertificateError."""
        import aiohttp

        auth = make_auth()

        @asynccontextmanager
        async def _raise(*args, **kwargs):
            raise aiohttp.ClientConnectorCertificateError(MagicMock(), MagicMock())
            yield  # type: ignore[misc]

        auth._session.post = _raise
        with pytest.raises(SslCertificateError):
            await auth._login_userpass()


class TestVerifyApiKey:
    """Tests for UniFiAuth._verify_api_key - tested in isolation via make_auth()."""

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
        """A generic aiohttp.ClientError in _verify_api_key must raise CannotConnectError."""
        import aiohttp

        auth = make_auth({"api_key": "test-key", "verify_ssl": True})

        @asynccontextmanager
        async def _raise(*args, **kwargs):
            raise aiohttp.ClientConnectionError("connection refused")
            yield  # type: ignore[misc]

        auth._session.get = _raise
        with pytest.raises(CannotConnectError):
            await auth._verify_api_key()


class TestAuthenticate:
    """Tests for UniFiAuth.authenticate — method auto-detection and fallback.

    Exercised entirely at the HTTP layer (mocked session responses), not by
    monkeypatching the private _verify_api_key/_login_userpass methods, so
    these tests fail if the real request/response handling breaks.
    """

    @pytest.mark.asyncio
    async def test_apikey_method_used_when_configured(self):
        auth = make_auth({"api_key": "my-key", "auth_method": "apikey", "verify_ssl": False})
        auth._session.get = _make_response(200)

        result = await auth.authenticate()

        assert result == "apikey"
        assert auth.method == "apikey"
        assert auth.authenticated is True

    @pytest.mark.asyncio
    async def test_apikey_fallback_to_userpass_when_key_invalid(self):
        """If api_key present but method not explicitly set to apikey, fall back to userpass on InvalidAuthError."""
        auth = make_auth({"api_key": "bad-key", "verify_ssl": False})
        auth._session.get = _make_response(401)
        auth._session.post = _make_response(200)

        result = await auth.authenticate()

        assert result == "userpass"
        assert auth.method == "userpass"
        assert auth.authenticated is True

    @pytest.mark.asyncio
    async def test_explicit_apikey_method_does_not_fallback(self):
        """If auth_method=apikey is explicit, InvalidAuthError must propagate (no fallback)."""
        auth = make_auth({"api_key": "bad-key", "auth_method": "apikey", "verify_ssl": False})
        auth._session.get = _make_response(401)

        post_calls = []
        auth._session.post = lambda *a, **k: post_calls.append(1)

        with pytest.raises(InvalidAuthError):
            await auth.authenticate()
        assert post_calls == [], "userpass login must not be attempted"


class TestSslCertificateError:
    """SslCertificateError is raised on TLS certificate failures, not CannotConnectError."""

    def test_ssl_cert_error_is_subclass_of_cannot_connect(self):
        assert issubclass(SslCertificateError, CannotConnectError)
