"""Top-level pytest config.

Windows-only workaround: neutralise pytest-socket's full-disable so asyncio's
ProactorEventLoop can build its socketpair-backed self-pipe. See the
``pytest_configure`` docstring below for the full explanation.
"""

from __future__ import annotations

import sys


def pytest_configure(config):  # noqa: ARG001
    """Replace ``pytest_socket.disable_socket`` with a no-op on Windows.

    Home Assistant's test conftest (loaded via
    pytest-homeassistant-custom-component) installs its own
    ``pytest_runtest_setup`` hook that runs before every test:

        pytest_socket.socket_allow_hosts(["127.0.0.1"])
        pytest_socket.disable_socket(allow_unix_socket=True)

    The first call patches ``socket.socket.connect`` so only loopback is
    reachable. The second call swaps ``socket.socket`` for a ``GuardedSocket``
    subclass whose ``__new__`` raises ``SocketBlockedError`` unless ``family``
    is ``AF_UNIX``. On Linux/macOS asyncio uses ``os.pipe()`` for its
    event-loop self-pipe so the swap is invisible there. On Windows the
    default ``ProactorEventLoop`` calls ``socket.socketpair()`` (loopback TCP)
    inside ``__init__``; the GuardedSocket raises in ``__new__``, ``_ssock``
    is never assigned, and the half-initialised loop later crashes in
    ``__del__`` with `'ProactorEventLoop' object has no attribute '_ssock'`.
    Every async test fails before user code runs.

    Replacing ``pytest_socket.disable_socket`` with a no-op leaves the prior
    ``socket_allow_hosts(["127.0.0.1"])`` call in place: AF_INET sockets can
    be created freely, but ``connect()`` still only permits loopback, so
    external network egress remains blocked. HA's hook references the
    function via the module attribute (``pytest_socket.disable_socket(...)``),
    so the replacement is picked up. ``pytest_configure`` runs before any
    test/fixture, ensuring the patch is in place for the very first hook
    invocation. No-op on Linux/macOS.
    """
    if sys.platform != "win32":
        return

    import pytest_socket  # noqa: PLC0415

    pytest_socket.disable_socket = lambda **kwargs: None
