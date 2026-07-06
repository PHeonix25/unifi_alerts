"""Regression tests for `scripts/_console.py`.

Issue #148: on Windows shells whose stdout codec is `cp1252` (the default
on most non-internationalised Windows installs), `print("✅ …")` raises
`UnicodeEncodeError` and crashes the standalone scripts in `scripts/`.

`use_utf8_console()` forces stdout/stderr to UTF-8 so the scripts behave
identically on Linux, macOS, and Windows without contributors needing to
export `PYTHONIOENCODING=utf-8`. These tests pin that contract.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONSOLE_PATH = REPO_ROOT / "scripts" / "_console.py"
AFFECTED_SCRIPTS = (
    "run_lint.py",
    "run_typecheck.py",
    "validate_hacs.py",
    "validate_docs.py",
    "check_translations.py",
)


def _load_console() -> ModuleType:
    """Import `scripts/_console.py` by file path.

    `scripts/` has no `__init__.py` (it is a flat directory of standalone
    entry points), so a normal `from scripts._console import …` does not
    resolve. We replicate Python's invocation behaviour: when a script is
    run as `python scripts/run_lint.py`, its directory is added to
    `sys.path[0]` and the helper is importable as `_console`.
    """
    spec = importlib.util.spec_from_file_location("_console", CONSOLE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestUseUtf8Console:
    def test_reconfigures_both_streams_to_utf8_replace(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both stdout and stderr are reconfigured with errors='replace'."""
        fake_stdout = MagicMock()
        fake_stderr = MagicMock()
        monkeypatch.setattr(sys, "stdout", fake_stdout)
        monkeypatch.setattr(sys, "stderr", fake_stderr)

        _load_console().use_utf8_console()

        fake_stdout.reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")
        fake_stderr.reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")

    def test_is_noop_when_reconfigure_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Streams that don't expose `reconfigure` (e.g. swapped by a test
        harness) must be skipped silently, not crash."""

        class _NoReconfigure:
            pass

        monkeypatch.setattr(sys, "stdout", _NoReconfigure())
        monkeypatch.setattr(sys, "stderr", _NoReconfigure())

        # Must not raise.
        _load_console().use_utf8_console()

    def test_emoji_print_does_not_crash_after_reconfigure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end: a TextIOWrapper around a cp1252 buffer crashes on
        emoji before `use_utf8_console()` runs, and succeeds after."""
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp1252", write_through=True)
        monkeypatch.setattr(sys, "stdout", stream)
        monkeypatch.setattr(sys, "stderr", stream)

        # Sanity check: cp1252 cannot encode U+2705, baseline must crash.
        with pytest.raises(UnicodeEncodeError):
            print("✅ baseline")

        _load_console().use_utf8_console()

        # After reconfigure, the same print succeeds and the UTF-8 bytes
        # for U+2705 (E2 9C 85) appear in the underlying buffer.
        print("✅ after fix")
        stream.flush()
        assert b"\xe2\x9c\x85" in raw.getvalue()


class TestAffectedScriptsWireTheHelper:
    """Each of the 5 scripts named in #148 must import and call the helper.

    A purely textual check is brittle, but it catches the common
    regression: someone adds a 6th unicode-emitting script (or refactors
    one of the 5) and forgets the two-line wiring.
    """

    @pytest.mark.parametrize("script", AFFECTED_SCRIPTS)
    def test_script_imports_and_invokes_helper(self, script: str) -> None:
        source = (REPO_ROOT / "scripts" / script).read_text(encoding="utf-8")
        assert "from _console import use_utf8_console" in source, (
            f"scripts/{script} is missing the _console import — see #148"
        )
        assert "use_utf8_console()" in source, (
            f"scripts/{script} imports the helper but never calls it — see #148"
        )
