"""Top-level pytest config.

The only thing this file does is patch around a Windows-specific interaction
between pytest-socket (pulled in by pytest-homeassistant-custom-component)
and asyncio's default ProactorEventLoop. See `_windows_loopback_sockets`.
"""

from __future__ import annotations

import sys
from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def _windows_loopback_sockets() -> Generator[None, None, None]:
    """Permit loopback sockets on Windows so asyncio can build its self-pipe.

    pytest-homeassistant-custom-component disables all sockets via
    pytest-socket. On Linux/macOS asyncio uses os.pipe() for the event-loop
    self-pipe, so blocking sockets is harmless. On Windows the default
    ProactorEventLoop calls socket.socketpair() (loopback TCP) inside
    __init__; with sockets blocked the call raises, _ssock is never assigned,
    and the half-initialised loop later crashes in __del__ with
    "'ProactorEventLoop' object has no attribute '_ssock'", failing every
    async test before user code runs.

    Allowing 127.0.0.1 / ::1 fixes the self-pipe without permitting any
    external network traffic. No-op off Windows.
    """
    if sys.platform != "win32":
        yield
        return

    from pytest_socket import socket_allow_hosts

    socket_allow_hosts(["127.0.0.1", "::1", "localhost"], allow_unix_socket=True)
    yield
