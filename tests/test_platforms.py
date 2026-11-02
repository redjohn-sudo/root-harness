"""macOS, Linux and Windows from one machine: the system is simulated
(sys.platform, shutil.which, the commands run), so each branch is checked
wherever the tests run. Nothing here touches the real clipboard, keychain or
a window.
Run:  .venv/bin/python -m pytest -q tests/test_platforms.py"""
import base64
import json
import os
import stat
import struct
import subprocess
import sys
import tempfile
import types
import webbrowser
from pathlib import Path
from unittest import mock

import pytest

os.environ.setdefault("ROOT_HARNESS_HOME", tempfile.mkdtemp(prefix="rh-test-"))

from rootharness import account, brains, bridge_claude, instinct, system, tools, window   # noqa: E402

PNG = Path(window.__file__).parent / "ui" / "icon.png"


def on(monkeypatch, platform, **env):
    """Pretend to be on `platform` (win32, darwin, linux) with this environment."""
    monkeypatch.setattr(sys, "platform", platform)
    for k in ("WAYLAND_DISPLAY", "DISPLAY", "PYWEBVIEW_GUI", "QT_QPA_PLATFORM", "LANG", "LC_ALL", "LC_CTYPE"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def fake_which(table):
    """shutil.which answering from {name: path}; anything else is missing."""
    return lambda name, mode=os.F_OK | os.X_OK, path=None: table.get(name) if path is None else None


# -- finding a program ---------------------------------------------------------------

def test_npm_scripts_are_found_on_windows(monkeypatch):
    on(monkeypatch, "win32")
    monkeypatch.setattr(system.shutil, "which", fake_which({"npx": r"C:\Users\me\AppData\Roaming\npm\npx.CMD"}))
    assert system.cmd("npx", "-y", "server") == [r"C:\Users\me\AppData\Roaming\npm\npx.CMD", "-y", "server"]


def test_install_folders_after_the_path(monkeypatch):
    on(monkeypatch, "linux")
    seen = []

    def which(name, mode=os.F_OK | os.X_OK, path=None):
        seen.append(path)
        return str(Path(path) / name) if path and path.endswith(str(Path(".local") / "bin")) else None
    monkeypatch.setattr(system.shutil, "which", which)
    assert system.which("claude") == str(Path.home() / ".local" / "bin" / "claude")
    assert seen[0] is None                     # the PATH is asked first


def test_missing_program_keeps_its_name(monkeypatch):
    on(monkeypatch, "linux")
    monkeypatch.setattr(system.shutil, "which", fake_which({}))
    assert system.cmd("gh", "api", "user") == ["gh", "api", "user"]


def test_cmd_script_refuses_what_cmd_exe_would_read(monkeypatch):
    on(monkeypatch, "win32")
    monkeypatch.setattr(system.shutil, "which", fake_which({"codex": r"C:\npm\codex.cmd", "gh": r"C:\gh\gh.exe"}))
    assert system.cmd("codex", "app-server")[1:] == ["app-server"]
    with pytest.raises(OSError):
        system.cmd("codex", "x & calc")
    assert system.cmd("gh", "api", "a?b=1&c=2")[0].endswith("gh.exe")     # a real .exe takes anything


# -- running it ------------------------------------------------------------------------

def test_text_is_utf8_and_windowless_on_windows(monkeypatch):
    on(monkeypatch, "win32")
    got = {}
    monkeypatch.setattr(system.subprocess, "run", lambda args, **kw: got.update(kw) or types.SimpleNamespace(stdout=""))
    system.run(["gh", "api", "user"], capture_output=True, text=True)
    assert got["encoding"] == "utf-8" and got["errors"] == "replace"
    assert got["creationflags"] & system.NO_WINDOW


def test_no_creationflags_off_windows(monkeypatch):
    on(monkeypatch, "darwin")
    got = {}
    monkeypatch.setattr(system.subprocess, "run", lambda args, **kw: got.update(kw))
    system.run(["true"], capture_output=True)
    assert "creationflags" not in got and "encoding" not in got     # bytes stay bytes


def test_json_lines_in_utf8_without_crlf():
    echo = "import sys\nfor l in sys.stdin.buffer: sys.stdout.buffer.write(l); sys.stdout.buffer.flush()"
    p = system.popen_lines([sys.executable, "-c", echo], stderr=subprocess.DEVNULL)
    try:
        p.stdin.write(json.dumps({"text": "é ü 日本"}, ensure_ascii=False) + "\n")
        p.stdin.flush()
        line = p.stdout.readline()
    finally:
        p.kill()
        p.wait()
    assert json.loads(line) == {"text": "é ü 日本"}
    assert not line.endswith("\r\n")


# -- the agent's shell -------------------------------------------------------------------

def test_powershell_on_windows(monkeypatch):
    on(monkeypatch, "win32")
    monkeypatch.setattr(system.shutil, "which", fake_which({"powershell": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"}))
    argv = system.shell_argv('Get-ChildItem "C:\\Program Files" | Select -First 1')
    assert argv[0].endswith("powershell.exe") and "-EncodedCommand" in argv and "-NonInteractive" in argv
    script = base64.b64decode(argv[-1]).decode("utf-16-le")
    assert script.endswith('Get-ChildItem "C:\\Program Files" | Select -First 1')
    assert "UTF8Encoding" in script                      # its output comes back in UTF-8
    assert "PowerShell" in system.shell_hint() and "Windows" in system.shell_hint()


def test_pwsh_preferred_and_cmd_as_last_resort(monkeypatch):
    on(monkeypatch, "win32", ComSpec=r"C:\Windows\system32\cmd.exe")
    monkeypatch.setattr(system.shutil, "which", fake_which({"pwsh": r"C:\pwsh\pwsh.exe", "powershell": r"C:\ps\powershell.exe"}))
    assert system.shell_argv("dir")[0] == r"C:\pwsh\pwsh.exe"
    monkeypatch.setattr(system.shutil, "which", fake_which({}))
    line = system.shell_argv("dir")
    assert isinstance(line, str) and "cmd.exe" in line and "chcp 65001" in line and line.endswith('dir"')
    assert system.shell_name() == "cmd.exe"


def test_sh_elsewhere(monkeypatch):
    for platform in ("darwin", "linux"):
        on(monkeypatch, platform)
        assert system.shell_argv("ls ~") == ["/bin/sh", "-c", "ls ~"]
        assert "/bin/sh" in system.shell_hint()


@pytest.mark.skipif(sys.platform == "win32", reason="runs a real /bin/sh")
def test_run_command_runs_and_a_stuck_one_is_stopped_whole():
    with mock.patch.object(tools.permissions, "ask", return_value=True):
        assert tools.run_command("printf 'héllo'; echo err >&2").startswith("héllo")
    out, code = system.run_shell("sleep 30 & sleep 30", timeout=1)
    assert code is None and "stopped" in out


def test_run_command_tells_the_agent_its_shell():
    assert system.shell_hint() in tools.REGISTRY["run_command"]["desc"]


def test_windows_arguments_keep_backslashes(monkeypatch):
    on(monkeypatch, "win32")
    assert system.split_args(r'C:\mcp\server.py --root "C:\My Files"') == [r"C:\mcp\server.py", "--root", r"C:\My Files"]
    on(monkeypatch, "linux")
    assert system.split_args("server.py --root 'a b'") == ["server.py", "--root", "a b"]


# -- the clipboard --------------------------------------------------------------------------

def capture_runs(monkeypatch, fail=()):
    ran = []

    def run(args, **kw):
        ran.append((args, kw))
        if Path(args[0]).name in fail:
            raise subprocess.CalledProcessError(1, args)
        return types.SimpleNamespace(returncode=0)
    monkeypatch.setattr(system, "run", run)
    return ran


def test_clipboard_mac_in_utf8(monkeypatch):
    on(monkeypatch, "darwin")
    monkeypatch.setattr(system.shutil, "which", fake_which({"pbcopy": "/usr/bin/pbcopy"}))
    ran = capture_runs(monkeypatch)
    assert system.copy("friend#k7f2qa9m é") == (True, "")
    args, kw = ran[0]
    assert args == ["/usr/bin/pbcopy"] and kw["input"] == "friend#k7f2qa9m é".encode()
    assert kw["env"]["LANG"].endswith("UTF-8")           # a GUI launch has no locale: pbcopy would misread it


def test_clipboard_wayland_first_then_x11(monkeypatch):
    on(monkeypatch, "linux", WAYLAND_DISPLAY="wayland-0")
    monkeypatch.setattr(system.shutil, "which", fake_which({"wl-copy": "/usr/bin/wl-copy", "xclip": "/usr/bin/xclip"}))
    ran = capture_runs(monkeypatch, fail={"wl-copy"})
    assert system.copy("x")[0]
    assert [Path(a[0]).name for a, _ in ran] == ["wl-copy", "xclip"]
    assert ran[0][1]["stdout"] == subprocess.DEVNULL     # wl-copy stays behind: never wait on its output


def test_clipboard_x11(monkeypatch):
    on(monkeypatch, "linux", DISPLAY=":0")
    monkeypatch.setattr(system.shutil, "which", fake_which({"xsel": "/usr/bin/xsel", "wl-copy": "/usr/bin/wl-copy"}))
    ran = capture_runs(monkeypatch)
    assert system.copy("x")[0]
    assert ran[0][0] == ["/usr/bin/xsel", "--clipboard", "--input"]


def test_clipboard_missing_says_what_to_install(monkeypatch):
    on(monkeypatch, "linux", DISPLAY=":0")
    monkeypatch.setattr(system.shutil, "which", fake_which({}))
    ok, why = system.copy("x")
    assert not ok and "wl-clipboard" in why and "xclip" in why
    assert system.clipboard_status()["available"] is False


def test_clipboard_windows_unicode_then_powershell(monkeypatch):
    on(monkeypatch, "win32")
    monkeypatch.setattr(system.shutil, "which", fake_which({"powershell": r"C:\ps\powershell.exe"}))
    ran = capture_runs(monkeypatch)
    with mock.patch.object(system, "_win_clipboard", return_value=True) as api:
        assert system.copy("日本 é") == (True, "")
    api.assert_called_once_with("日本 é")
    assert ran == []                                     # never clip.exe
    with mock.patch.object(system, "_win_clipboard", side_effect=OSError("no user32")):
        assert system.copy("é")[0]
    assert "Set-Clipboard" in ran[0][0][-1] and ran[0][1]["input"] == "é".encode()


def test_window_copy_text_stays_a_bool(monkeypatch):
    api = object.__new__(window.Api)
    monkeypatch.setattr(system, "copy", lambda t: (False, "No clipboard tool found"))
    assert api.copy_text("x") is False
    monkeypatch.setattr(system, "copy", lambda t: (True, ""))
    assert api.copy_text("x") is True


# -- opening a file or a link ----------------------------------------------------------------

def test_open_link_in_the_browser(monkeypatch):
    on(monkeypatch, "linux")
    with mock.patch.object(webbrowser, "open", return_value=True) as wb:
        assert system.open_target("https://github.com/login/device")
    wb.assert_called_once()


def test_open_file_per_system(monkeypatch):
    opened = []
    monkeypatch.setattr(system, "popen", lambda args, **kw: opened.append(args))
    monkeypatch.setattr(system.shutil, "which", fake_which({"xdg-open": "/usr/bin/xdg-open", "open": "/usr/bin/open"}))
    on(monkeypatch, "darwin")
    system.open_target("notes/a b.txt")
    on(monkeypatch, "linux")
    system.open_target("notes/a b.txt")
    assert opened == [["/usr/bin/open", "notes/a b.txt"], ["/usr/bin/xdg-open", "notes/a b.txt"]]
    on(monkeypatch, "win32")
    with mock.patch.object(system.os, "startfile", create=True) as start:
        assert system.open_target(r"C:\Users\me\notes.txt")
    start.assert_called_once_with(r"C:\Users\me\notes.txt")


def test_open_without_any_opener(monkeypatch):
    on(monkeypatch, "linux")
    monkeypatch.setattr(system.shutil, "which", fake_which({}))
    assert system.open_target("notes/x") is False


# -- swapping a file in whole ------------------------------------------------------------------

def test_replace_retries_a_busy_file_on_windows(monkeypatch, tmp_path):
    on(monkeypatch, "win32")
    monkeypatch.setattr(system.time, "sleep", lambda s: None)
    real, calls = os.replace, []

    def flaky(a, b):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError(32, "being used by another process")
        real(a, b)
    monkeypatch.setattr(system.os, "replace", flaky)
    (tmp_path / "a").write_text("new")
    system.replace(tmp_path / "a", tmp_path / "b")
    assert (tmp_path / "b").read_text() == "new" and len(calls) == 3


def test_replace_does_not_retry_elsewhere(monkeypatch, tmp_path):
    on(monkeypatch, "linux")
    monkeypatch.setattr(system.os, "replace", mock.Mock(side_effect=PermissionError(13, "denied")))
    with pytest.raises(PermissionError):
        system.replace(tmp_path / "a", tmp_path / "b")
    assert system.os.replace.call_count == 1


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes")
def test_atomic_write_private_and_clean(tmp_path):
    target = tmp_path / "deep" / "keys.env"
    system.atomic_write(target, "A=1\n", private=True)
    assert target.read_text(encoding="utf-8") == "A=1\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert list(target.parent.glob("*.tmp")) == []
    target.chmod(0o644)                                  # an older file: replaced by a private one
    system.atomic_write(target, "A=2\n", private=True)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_keys_file_is_private_from_the_first_byte(monkeypatch, tmp_path):
    monkeypatch.setattr(brains, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(brains, "HOME", tmp_path)
    seen = []
    real = system.atomic_write
    monkeypatch.setattr(system, "atomic_write", lambda p, t, private=False: seen.append(private) or real(p, t, private))
    assert brains.save_key("DEEPSEEK_API_KEY", "sk-test")
    assert seen == [True] and brains.key("DEEPSEEK_API_KEY") == "sk-test"


# -- pictures -------------------------------------------------------------------------------------

def test_no_disk_converter_on_windows(monkeypatch):
    on(monkeypatch, "win32")
    monkeypatch.setattr(system.shutil, "which", fake_which({"convert": r"C:\Windows\System32\convert.exe"}))
    ran = capture_runs(monkeypatch)
    assert system.convert_image("a.heic", "b.jpg") is False and ran == []


def test_imagemagick_on_linux_and_sips_on_mac(monkeypatch, tmp_path):
    out = tmp_path / "b.jpg"
    out.write_bytes(b"jpg")
    ran = capture_runs(monkeypatch)
    on(monkeypatch, "linux")
    monkeypatch.setattr(system.shutil, "which", fake_which({"convert": "/usr/bin/convert"}))
    assert system.convert_image("a.heic", out, max_side=1600, quality=70)
    assert ran[-1][0][0] == "/usr/bin/convert" and "1600x1600>" in ran[-1][0]
    on(monkeypatch, "darwin")
    monkeypatch.setattr(system.shutil, "which", fake_which({"sips": "/usr/bin/sips"}))
    assert system.convert_image("a.png", out, max_side=1600, quality=70)
    assert ran[-1][0] == ["sips", "-Z", "1600", "-s", "format", "jpeg", "-s", "formatOptions", "70", "a.png", "--out", str(out)]


def test_windows_icon_from_the_png(tmp_path):
    ico = tmp_path / "icon.ico"
    assert system.png_to_ico(PNG, ico)
    data = ico.read_bytes()
    assert struct.unpack("<HHH", data[:6]) == (0, 1, 4)
    assert data[6] == 0 and data[7] == 0                 # first image: 256 x 256


def test_window_icon_per_system(monkeypatch, tmp_path):
    on(monkeypatch, "linux")
    assert system.window_icon(PNG, tmp_path) == str(PNG)
    on(monkeypatch, "darwin")
    assert system.window_icon(PNG, tmp_path) is None      # the Dock icon is set apart
    on(monkeypatch, "win32")
    assert system.window_icon(PNG, tmp_path) == str(tmp_path / "icon.ico")
    assert (tmp_path / "icon.ico").exists()


# -- the window's toolkit ---------------------------------------------------------------------------

def test_linux_prefers_gtk(monkeypatch):
    on(monkeypatch, "linux", DISPLAY=":0")
    monkeypatch.setattr(system, "_gtk_ok", lambda: True)
    monkeypatch.setattr(system, "_qt_ok", lambda: True)
    assert system.pick_gui() == "gtk"


def test_linux_falls_back_to_qt_with_xwayland_behind(monkeypatch):
    on(monkeypatch, "linux", WAYLAND_DISPLAY="wayland-0")
    monkeypatch.setattr(system, "_gtk_ok", lambda: False)
    monkeypatch.setattr(system, "_qt_ok", lambda: True)
    assert system.pick_gui() == "qt"
    assert os.environ["QT_QPA_PLATFORM"] == "wayland;xcb"


def test_linux_without_toolkit_and_others(monkeypatch):
    on(monkeypatch, "linux", DISPLAY=":0")
    monkeypatch.setattr(system, "_gtk_ok", lambda: False)
    monkeypatch.setattr(system, "_qt_ok", lambda: False)
    assert system.pick_gui() is None
    monkeypatch.setattr(system, "_qt_ok", lambda: True)
    monkeypatch.setenv("PYWEBVIEW_GUI", "gtk")
    assert system.pick_gui() is None                     # the user's choice: pywebview reads it
    for platform in ("darwin", "win32"):
        on(monkeypatch, platform)
        assert system.pick_gui() is None


def test_start_passes_toolkit_and_icon(monkeypatch):
    on(monkeypatch, "linux", DISPLAY=":0")
    monkeypatch.setattr(system, "pick_gui", lambda: "qt")
    started = {}
    monkeypatch.setattr(window, "Api", lambda: types.SimpleNamespace(bind=lambda w: None))
    monkeypatch.setattr(window.webview, "create_window", lambda *a, **kw: started.update(window=kw))
    monkeypatch.setattr(window.webview, "start", lambda *a, **kw: started.update(start=kw, args=a))
    window.start()
    assert started["window"]["text_select"] is True and started["window"]["zoomable"] is False
    assert started["start"]["gui"] == "qt" and started["start"]["icon"].endswith("icon.png")


def test_webview2_missing_is_said_in_the_window(monkeypatch):
    on(monkeypatch, "win32")
    w = mock.Mock()
    monkeypatch.setattr(window.webview, "renderer", "mshtml", raising=False)
    window._check_engine(w)
    assert "WebView2" in w.load_html.call_args[0][0]
    w.reset_mock()
    monkeypatch.setattr(window.webview, "renderer", "edgechromium", raising=False)
    window._check_engine(w)
    w.load_html.assert_not_called()


# -- Claude Code on Windows: a real claude.exe -------------------------------------------------------

def test_claude_cmd_alone_is_not_enough_on_windows(monkeypatch):
    on(monkeypatch, "win32")
    monkeypatch.setattr(bridge_claude, "_bundled", lambda: None)
    monkeypatch.setattr(system.shutil, "which", fake_which({"claude": r"C:\npm\claude.cmd"}))
    assert bridge_claude.cli_path() is None
    st = brains.status({"kind": "claude"})
    assert not st["ready"] and "claude.exe" in st["why"]


def test_claude_exe_or_bundled_on_windows(monkeypatch):
    on(monkeypatch, "win32")
    monkeypatch.setattr(bridge_claude, "_bundled", lambda: None)
    monkeypatch.setattr(system.shutil, "which", fake_which({"claude": r"C:\Users\me\.local\bin\claude.exe"}))
    assert bridge_claude.cli_options() == {"cli_path": r"C:\Users\me\.local\bin\claude.exe"}
    monkeypatch.setattr(bridge_claude, "_bundled", lambda: Path(r"C:\sdk\_bundled\claude.exe"))
    assert bridge_claude.cli_path() == str(Path(r"C:\sdk\_bundled\claude.exe"))


def test_claude_unchanged_on_mac(monkeypatch):
    on(monkeypatch, "darwin")
    monkeypatch.setattr(system.shutil, "which", fake_which({"claude": "/opt/homebrew/bin/claude"}))
    assert bridge_claude.cli_options() == {}             # the SDK finds it as before
    assert brains.status({"kind": "claude"}) == {"ready": True}


def test_gh_browser_is_a_real_noop(monkeypatch):
    on(monkeypatch, "win32")
    assert window._no_browser() == "cmd /c rem"
    on(monkeypatch, "linux")
    assert window._no_browser() == "true"


# -- iMessage: macOS only, quietly off elsewhere -------------------------------------------------------

def test_instinct_off_outside_macos(monkeypatch):
    on(monkeypatch, "linux")
    monkeypatch.setattr(instinct, "HANDLE", "someone@example.com")
    with mock.patch.object(instinct.sqlite3, "connect", side_effect=AssertionError("never opened")):
        assert instinct.available() is False
        assert instinct.history() == [] and instinct.since(5) == [] and instinct.last_id() == 0
    ok, why = instinct.send("hello")
    assert not ok and "macOS" in why
    api = object.__new__(window.Api)
    assert "macOS" in api.instinct_available()["why"]


# -- the keychain: never the key in a plain file ----------------------------------------------------------

class NoKeychain:
    def __init__(self, backend):
        self.backend, self.stored = backend, []

    def get_keyring(self):
        return self.backend

    def get_password(self, *a):
        from keyring.errors import NoKeyringError
        raise NoKeyringError("No recommended backend was available.")

    def set_password(self, *a):
        self.stored.append(a)

    def delete_password(self, *a):
        pass


def test_no_keychain_on_linux(monkeypatch):
    from keyring.backends import fail
    on(monkeypatch, "linux")
    kr = NoKeychain(fail.Keyring())
    monkeypatch.setattr(account, "_keyring", lambda: kr)
    k = account.keychain()
    assert not k["available"] and "Secret Service" in k["why"]
    monkeypatch.setattr(account, "_load", lambda: {"npub": "x", "stay": False})
    assert account.set_stay(True, object()) is False
    assert kr.stored == []                                # nothing written anywhere


def test_plain_file_keyring_does_not_count(monkeypatch):
    plain = type("PlaintextKeyring", (), {"__module__": "keyrings.alt.file"})()
    monkeypatch.setattr(account, "_keyring", lambda: NoKeychain(plain))
    assert account.keychain()["available"] is False


def test_account_can_be_made_without_keychain(monkeypatch):
    from keyring.backends import fail
    monkeypatch.setattr(account, "_keyring", lambda: NoKeychain(fail.Keyring()))
    with mock.patch.object(account, "_save") as save:
        keys, why = account.create("someone", "a long password", "a long password")
    assert why is None and keys is not None
    save.assert_called_once()


def test_auto_sign_in_without_keychain_asks_the_password(monkeypatch):
    from keyring.backends import fail
    monkeypatch.setattr(account, "_keyring", lambda: NoKeychain(fail.Keyring()))
    monkeypatch.setattr(account, "_load", lambda: {"npub": "x", "stay": True})
    assert account.auto() is None


# -- MCP servers: the full path, so npx.cmd runs on Windows ---------------------------------------------------

def test_mcp_command_resolved(monkeypatch):
    import asyncio
    from contextlib import AsyncExitStack, asynccontextmanager
    from rootharness import mcp_tools
    on(monkeypatch, "win32")
    monkeypatch.setattr(system.shutil, "which", fake_which({"npx": r"C:\npm\npx.cmd"}))
    seen = {}

    @asynccontextmanager
    async def fake_stdio(params):
        seen["command"], seen["args"] = params.command, params.args
        yield ("r", "w")
    monkeypatch.setattr(mcp_tools, "stdio_client", fake_stdio)

    async def go():
        async with AsyncExitStack() as stack:
            return await mcp_tools._streams({"command": "npx", "args": ["-y", "pkg"]}, stack)
    assert asyncio.run(go()) == ("r", "w")
    assert seen == {"command": r"C:\npm\npx.cmd", "args": ["-y", "pkg"]}


def test_mcp_add_splits_windows_paths(monkeypatch):
    from rootharness import mcp_tools
    on(monkeypatch, "win32")
    got = {}
    monkeypatch.setattr(mcp_tools, "add_server", lambda name, command, parts, deny: got.update(parts=parts) or {"ok": False})
    api = object.__new__(window.Api)
    api.mcp_add("fs", "python", r'C:\srv\fs.py --root "C:\My Files"')
    assert got["parts"] == [r"C:\srv\fs.py", "--root", r"C:\My Files"]
