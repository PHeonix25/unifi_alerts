"""Top-level pytest config.

Windows-only workarounds for two issues that don't manifest on Linux/macOS.
Both are no-ops on non-Windows platforms.

1. ``WindowsSelectorEventLoopPolicy`` is installed at module load time so
   ``aiodns`` works. Python's default loop on Windows since 3.8 is the
   ``ProactorEventLoop``; ``aiodns`` (pulled in transitively via aiohttp/HA)
   raises ``RuntimeError: aiodns needs a SelectorEventLoop on Windows``
   otherwise. See https://github.com/saghul/aiodns/issues/86.

2. ``pytest_socket.disable_socket`` is rebound to a no-op in
   ``pytest_configure`` so asyncio's self-pipe (which uses
   ``socket.socketpair()`` even on the Selector loop) survives. See the
   ``pytest_configure`` docstring for the full explanation.
"""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


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
    event-loop self-pipe so the swap is invisible there. On Windows both
    ``ProactorEventLoop`` and ``SelectorEventLoop`` call
    ``socket.socketpair()`` (loopback TCP) inside ``__init__``; the
    ``GuardedSocket`` raises in ``__new__``, ``_ssock`` is never assigned,
    and the half-initialised loop later crashes in ``__del__`` with
    `'ProactorEventLoop' object has no attribute '_ssock'`. Every async test
    fails before user code runs.

    Replacing ``pytest_socket.disable_socket`` with a no-op leaves the prior
    ``socket_allow_hosts(["127.0.0.1"])`` call in place: AF_INET sockets can
    be created freely, but ``connect()`` still only permits loopback, so
    external network egress remains blocked. HA's hook references the
    function via the module attribute, so the rebind is picked up.
    ``pytest_configure`` runs before any test/fixture, ensuring the patch is
    in place for the very first hook invocation. No-op on Linux/macOS.
    """
    if sys.platform != "win32":
        return

    import pytest_socket  # noqa: PLC0415

    pytest_socket.disable_socket = lambda **kwargs: None
