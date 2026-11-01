#!/usr/bin/env python3
"""Smoke test of the real window: start root-harness as `app.py` does, in a
throwaway home, wait for the page, check that JavaScript reaches Python
(`window.pywebview.api.account_state()`), that the interface drew itself and
that no JavaScript error came up, then close the window.

    python tests/smoke_gui.py                      # macOS, Windows, a Linux desktop
    xvfb-run -a python tests/smoke_gui.py          # Linux without a screen (CI)

Exit code 0 when everything answered, 1 otherwise; it gives up after
SMOKE_TIMEOUT seconds (60 by default). The name has no test_ prefix on purpose:
pytest does not collect it, so `pytest` stays fast and needs no screen.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

TIMEOUT = float(os.environ.get("SMOKE_TIMEOUT", "60"))
STARTED = time.monotonic()

# Always a fresh home: never your real account, memory or keychain entry.
HOME = tempfile.mkdtemp(prefix="rh-smoke-")
os.environ["ROOT_HARNESS_HOME"] = HOME
# An empty keychain, so a machine without one (CI, a bare Linux) behaves like a new user.
os.environ.setdefault("PYTHON_KEYRING_BACKEND", "keyring.backends.null.Keyring")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import webview  # noqa: E402

# What the page reports: errors thrown anywhere, rejected promises nobody caught.
TRAP = r"""
(function () {
  if (window.__smoke) return true;
  var s = window.__smoke = { errors: [], state: null };
  window.addEventListener('error', function (e) {
    s.errors.push('error: ' + (e.message || e.type) + (e.filename ? ' (' + e.filename + ':' + e.lineno + ')' : ''));
  });
  window.addEventListener('unhandledrejection', function (e) {
    var r = e.reason;
    s.errors.push('unhandled rejection: ' + (r && (r.message || r.name) || String(r)));
  });
  return true;
})()
"""

CALL = r"""
(function () {
  var s = window.__smoke;
  var api = window.pywebview && window.pywebview.api;
  if (!api || typeof api.account_state !== 'function') return 'no api';
  api.account_state().then(
    function (r) { s.state = { ok: r }; },
    function (e) { s.state = { error: String(e && (e.message || e.name) || e) }; });
  return 'called';
})()
"""

DRAWN = r"""
(function () {
  var b = document.body;
  if (!b) return 0;
  return b.querySelectorAll('*').length - b.querySelectorAll('script').length;
})()
"""


class Smoke:
    def __init__(self):
        self.window = None
        self.failures: list[str] = []
        self.notes: list[str] = []
        self.done = threading.Event()

    def left(self) -> float:
        return max(0.5, TIMEOUT - (time.monotonic() - STARTED) - 5)

    def until(self, what: str, js: str, ok, every: float = 0.25):
        """Evaluate js until ok(value) or the time runs out; the last value either way."""
        value = None
        end = time.monotonic() + self.left()
        while time.monotonic() < end:
            try:
                value = self.window.evaluate_js(js)
            except Exception as e:          # the page is (re)loading
                value = e
            if not isinstance(value, Exception) and ok(value):
                return value
            time.sleep(every)
        raise AssertionError(f"{what}: gave up (last answer: {value!r})")

    def probe(self):
        try:
            for _ in range(200):
                if self.window is not None:
                    break
                time.sleep(0.05)
            if self.window is None:
                raise AssertionError("root-harness never created its window")
            if not self.window.events.loaded.wait(self.left()):
                raise AssertionError("the page never finished loading")
            self.notes.append(f"page loaded in {time.monotonic() - STARTED:.1f} s")
            self.window.evaluate_js(TRAP)

            # 1. JavaScript reaches Python and gets an answer back
            called = self.window.evaluate_js(CALL)
            if called != "called":
                raise AssertionError(f"window.pywebview.api.account_state is missing ({called!r})")
            state = self.until("account_state() answer", "window.__smoke.state", lambda v: v is not None)
            if "error" in state:
                raise AssertionError(f"account_state() failed in Python: {state['error']}")
            st = state["ok"]
            if not isinstance(st, dict) or "unlocked" not in st:
                raise AssertionError(f"account_state() answered something unexpected: {st!r}")
            if st["unlocked"]:
                raise AssertionError("a brand-new home is already signed in: the home was not isolated")
            self.notes.append("api answered: account_state() " + json.dumps(st, sort_keys=True)[:160])

            # 2. the interface drew itself (a script error at start leaves an empty body)
            count = self.until("the interface on screen", DRAWN, lambda v: isinstance(v, (int, float)) and v >= 5)
            self.notes.append(f"interface drawn ({int(count)} elements)")

            # 3. a few seconds for the first calls the page makes on its own, then its errors
            time.sleep(min(3.0, self.left()))
            errors = self.window.evaluate_js("window.__smoke.errors") or []
            self.failures += [f"JavaScript {e}" for e in errors]
        except Exception as e:
            self.failures.append(f"{type(e).__name__}: {e}")
        finally:
            self.done.set()
            try:
                if self.window is not None:
                    self.window.destroy()
            except Exception:
                pass


class PythonErrors(logging.Handler):
    """pywebview logs an exception raised by an api method called from the page."""

    def __init__(self, smoke: Smoke):
        super().__init__(logging.ERROR)
        self.smoke = smoke

    def emit(self, record):
        self.smoke.failures.append("Python (pywebview): " + record.getMessage().strip().splitlines()[-1][:300])


def finish(smoke: Smoke, code: int | None = None):
    if code is None:
        code = 1 if smoke.failures or not smoke.done.is_set() else 0
    took = time.monotonic() - STARTED
    for n in smoke.notes:
        print("  " + n)
    for f in smoke.failures:
        print("  FAIL " + f)
    print(f"smoke_gui: {'OK' if code == 0 else 'FAILED'} in {took:.1f} s "
          f"(python {sys.version.split()[0]}, {sys.platform}, gui {gui_name(smoke)})")
    sys.stdout.flush()
    sys.stderr.flush()
    shutil.rmtree(HOME, ignore_errors=True)
    os._exit(code)      # the app's background threads (relays, sync) must not keep it alive


def gui_name(smoke: Smoke) -> str:
    try:
        return getattr(smoke.window.gui, "renderer", None) or smoke.window.gui.__name__.split(".")[-1]
    except Exception:
        return "?"


def main():
    smoke = Smoke()
    logging.getLogger("pywebview").addHandler(PythonErrors(smoke))

    def too_long():
        smoke.failures.append(f"no result after {TIMEOUT:g} s")
        finish(smoke, 1)
    watchdog = threading.Timer(TIMEOUT, too_long)
    watchdog.daemon = True
    watchdog.start()

    # Start the app exactly as app.py does, whichever backend it picks: only catch
    # the window it creates and run the probe once the GUI loop is up.
    real_create, real_start = webview.create_window, webview.start

    def create_window(*a, **kw):
        w = real_create(*a, **kw)
        if smoke.window is None:
            smoke.window = w
        return w

    def start(func=None, args=None, *rest, **kw):
        def both():
            threading.Thread(target=smoke.probe, daemon=True).start()
            if func is not None:
                if args is None:
                    func()
                elif isinstance(args, tuple):
                    func(*args)
                else:
                    func(args)
        return real_start(both, None, *rest, **kw)

    webview.create_window, webview.start = create_window, start
    try:
        from rootharness import window as app_window
        app_window.start()
    except Exception:
        smoke.failures.append("the app did not start:\n" + traceback.format_exc())
        finish(smoke, 1)
    if not smoke.done.is_set():
        smoke.failures.append("the window closed before the checks finished")
    finish(smoke)


if __name__ == "__main__":
    main()
