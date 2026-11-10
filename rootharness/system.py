"""
What differs between macOS, Linux and Windows, in one place.

  - finding a program (npm's claude.cmd / npx.cmd on Windows, ~/.local/bin
    when the app was not started from a terminal);
  - running it: text in UTF-8 whatever the system's code page, no console
    window popping up on Windows, the whole process tree stopped on a timeout;
  - the agent's shell: /bin/sh on macOS and Linux, PowerShell on Windows;
  - the clipboard, opening a file or a link, swapping a file in whole,
    converting a picture, the window's toolkit and icon.

Everything else in root-harness calls these instead of guessing the system.
"""
from __future__ import annotations

import base64
import io
import mimetypes
import os
import re
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import threading
import time
import webbrowser
import zlib
from pathlib import Path

PIPE, DEVNULL = subprocess.PIPE, subprocess.DEVNULL
NO_WINDOW = 0x08000000          # CREATE_NO_WINDOW: a console program, without its window


def windows() -> bool:
    return sys.platform == "win32"


def mac() -> bool:
    return sys.platform == "darwin"


def linux() -> bool:
    return sys.platform.startswith("linux")


def os_label() -> str:
    return "Windows" if windows() else "macOS" if mac() else "Linux" if linux() else sys.platform


# -- finding a program -------------------------------------------------------------

def _extra_dirs() -> list[Path]:
    """Where installers put programs that a GUI launch may not have on its PATH."""
    home = Path.home()
    if windows():
        env = os.environ
        dirs = [home / ".local" / "bin"]                       # Claude Code's native installer
        if env.get("APPDATA"):
            dirs.append(Path(env["APPDATA"]) / "npm")          # npm -g (claude.cmd, codex.cmd, npx.cmd)
        if env.get("LOCALAPPDATA"):
            local = Path(env["LOCALAPPDATA"])
            dirs += [local / "Microsoft" / "WinGet" / "Links",           # winget's portable installs
                     local / "Programs" / "Ollama", local / "Programs" / "GitHub CLI",
                     local / "Programs" / "Git" / "cmd", local / "Programs" / "nodejs"]
        for root in sorted({env.get("ProgramFiles"), env.get("ProgramW6432"), env.get("ProgramFiles(x86)")} - {None}):
            dirs += [Path(root) / "GitHub CLI", Path(root) / "Git" / "cmd", Path(root) / "nodejs"]
        dirs.append(home / "scoop" / "shims")
        return dirs
    dirs = [home / ".local" / "bin", home / ".npm-global" / "bin", home / ".claude" / "local", Path("/usr/local/bin")]
    if mac():
        dirs.insert(0, Path("/opt/homebrew/bin"))
    return dirs


def which(name: str) -> str | None:
    """The full path of a program: the PATH first (with .exe/.cmd/.bat on
    Windows), then the usual install folders."""
    hit = shutil.which(name)
    if hit or any(sep and sep in name for sep in (os.sep, os.altsep)):
        return hit
    for d in _extra_dirs():
        hit = shutil.which(name, path=str(d))
        if hit:
            return hit
    return None


# cmd.exe reads these itself when it runs a .cmd/.bat script, whatever the quoting
_CMD_META = set('"&|<>^%!\r\n')


def _batch(path: str) -> bool:
    return path.lower().endswith((".cmd", ".bat"))


def cmd(name: str, *args) -> list[str]:
    """[full path of the program, *args]. A missing program keeps its bare name,
    so running it raises FileNotFoundError (an OSError) as before."""
    exe = which(name) or name
    args = [str(a) for a in args]
    if windows() and _batch(exe) and any(_CMD_META & set(a) for a in args):
        raise OSError(f"{name} is a .cmd script here: refusing an argument cmd.exe would interpret")
    return [exe, *args]


# -- running it ----------------------------------------------------------------------

def _quiet(kw: dict) -> dict:
    """UTF-8 text (Windows defaults to its code page) and no console window."""
    if kw.get("text") or kw.get("universal_newlines") or kw.get("encoding"):
        kw.setdefault("encoding", "utf-8")
        kw.setdefault("errors", "replace")
    if windows():
        kw["creationflags"] = kw.get("creationflags", 0) | NO_WINDOW
    return kw


def run(args, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, **_quiet(kw))


def popen(args, **kw) -> subprocess.Popen:
    return subprocess.Popen(args, **_quiet(kw))


def popen_lines(args, **kw) -> subprocess.Popen:
    """A process spoken to in lines of UTF-8 JSON: '\\n' sent as is (no CRLF on
    Windows), any line ending read back."""
    p = popen(args, stdin=PIPE, stdout=PIPE, **kw)
    p.stdin = io.TextIOWrapper(p.stdin, encoding="utf-8", newline="\n", write_through=True)
    p.stdout = io.TextIOWrapper(p.stdout, encoding="utf-8", errors="replace")
    return p


def stop_tree(p: subprocess.Popen) -> None:
    """End a process and everything it started (a shell and its children)."""
    if p.poll() is not None:
        return
    try:
        if windows():
            run(["taskkill", "/F", "/T", "/PID", str(p.pid)], stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL, timeout=10)
        elif getattr(p, "own_group", False):
            os.killpg(p.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        p.kill()
    except OSError:
        pass


# -- the agent's shell ------------------------------------------------------------------

_PS_PRELUDE = ("$ProgressPreference = 'SilentlyContinue'\n"
               "try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch {}\n"
               "$OutputEncoding = New-Object System.Text.UTF8Encoding $false\n")


def _powershell() -> str | None:
    return which("pwsh") or which("powershell")


def shell_name() -> str:
    if windows():
        return "PowerShell" if _powershell() else "cmd.exe"
    return "/bin/sh"


def shell_hint() -> str:
    """One line for the agent: which shell its commands run in."""
    if windows():
        return (f"runs in {shell_name()} on Windows: use its syntax and Windows paths "
                "(C:\\...), not Unix commands")
    return f"runs in /bin/sh on {os_label()}"


def shell_argv(command: str):
    """The command line that runs `command` in this system's shell."""
    if windows():
        ps = _powershell()
        if ps:       # encoded: no quoting rules to get wrong between Python, Windows and PowerShell
            script = base64.b64encode((_PS_PRELUDE + command).encode("utf-16-le")).decode()
            return [ps, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", script]
        comspec = os.environ.get("ComSpec") or "cmd.exe"
        return f'"{comspec}" /d /s /c "chcp 65001>nul & {command}"'    # a string: cmd.exe has its own quoting
    return ["/bin/sh", "-c", command]


def run_shell(command: str, timeout: float = 60, cwd: str | None = None) -> tuple[str, int | None]:
    """(stdout + stderr, exit code); code None when it was stopped at the timeout."""
    p = popen(shell_argv(command), stdin=DEVNULL, stdout=PIPE, stderr=PIPE, text=True, cwd=cwd,
              start_new_session=not windows())
    p.own_group = not windows()
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        stop_tree(p)
        try:
            out, err = p.communicate(timeout=5)
        except (subprocess.TimeoutExpired, ValueError):
            out, err = "", ""
        return ((out or "") + (err or "")).lstrip("\ufeff") + f"\n(stopped: still running after {timeout:g} s)", None
    return ((out or "") + (err or "")).lstrip("\ufeff"), p.returncode


def split_args(text: str) -> list[str]:
    """Arguments typed in one line. On Windows backslashes stay (C:\\path), quotes group."""
    if not windows():
        return shlex.split(text or "")
    out = []
    for tok in shlex.split(text or "", posix=False):
        if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "\"'":
            tok = tok[1:-1]
        out.append(tok)
    return out


# -- the clipboard ------------------------------------------------------------------------

def _win_clipboard(text: str) -> bool:
    """The Windows clipboard, as Unicode (clip.exe would mangle anything not ASCII)."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes, user32.OpenClipboard.restype = [wintypes.HWND], wintypes.BOOL
    user32.SetClipboardData.argtypes, user32.SetClipboardData.restype = [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE
    kernel32.GlobalAlloc.argtypes, kernel32.GlobalAlloc.restype = [wintypes.UINT, ctypes.c_size_t], wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes, kernel32.GlobalLock.restype = [wintypes.HGLOBAL], wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    data = text.encode("utf-16-le") + b"\x00\x00"
    for _ in range(10):                      # another program may hold it for a moment
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return False
    try:
        user32.EmptyClipboard()
        h = kernel32.GlobalAlloc(0x0002, len(data))          # GMEM_MOVEABLE
        if not h:
            return False
        ptr = kernel32.GlobalLock(h)
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(h)
        if not user32.SetClipboardData(13, h):              # CF_UNICODETEXT; the system owns h from here
            kernel32.GlobalFree(h)
            return False
        return True
    finally:
        user32.CloseClipboard()


def clipboard_tools() -> list[list[str]]:
    """The copy commands to try, best first, for this system and session."""
    if mac():
        return [["pbcopy"]]
    if windows():
        ps = _powershell()
        return [[ps, "-NoProfile", "-NonInteractive", "-Command",
                 "[Console]::InputEncoding = New-Object System.Text.UTF8Encoding $false; "
                 "Set-Clipboard -Value ([Console]::In.ReadToEnd())"]] if ps else []
    wayland = [["wl-copy"]]
    x11 = [["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
    return wayland + x11 if os.environ.get("WAYLAND_DISPLAY") else x11 + wayland


def clipboard_status() -> dict:
    if windows() or any(which(t[0]) for t in clipboard_tools()):
        return {"available": True, "why": ""}
    return {"available": False, "why": "No clipboard tool found: install wl-clipboard (Wayland) or xclip (X11)."}


def copy(text: str) -> tuple[bool, str]:
    """Put text on the clipboard. (ok, why it failed)."""
    if windows():
        try:
            if _win_clipboard(text):
                return True, ""
        except Exception:                    # noqa: BLE001  (no user32: try PowerShell)
            pass
    env = None
    if mac() and not any(os.environ.get(k) for k in ("LC_ALL", "LC_CTYPE", "LANG")):
        env = {**os.environ, "LANG": "en_US.UTF-8"}         # pbcopy reads its input in the locale's encoding
    for tool in clipboard_tools():
        exe = tool[0] if windows() else which(tool[0])       # PowerShell's path is already resolved
        if not exe:
            continue
        try:
            # xclip and wl-copy stay behind to own the selection: never wait on their output
            run([exe, *tool[1:]], input=text.encode("utf-8"), stdout=DEVNULL, stderr=DEVNULL,
                check=True, timeout=5, env=env)
            return True, ""
        except (OSError, subprocess.SubprocessError):
            continue
    return False, clipboard_status()["why"] or "The clipboard did not take it."


# -- opening a file, a folder or a link ---------------------------------------------------

def open_target(target: str) -> bool:
    """Open a web link in the browser, or a file or folder with its usual app."""
    target = str(target)
    if re.match(r"(?i)https?://", target):
        return bool(webbrowser.open(target))
    try:
        if windows():
            os.startfile(target)            # noqa: S606  (the file's own app, as a double click)
            return True
        opener = ["open"] if mac() else next(([t[0], *t[1:]] for t in (["xdg-open"], ["gio", "open"]) if which(t[0])), None)
        if not opener:
            return False
        popen([which(opener[0]) or opener[0], *opener[1:], target], stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL)
        return True
    except OSError:
        return False


# -- a terminal window the person types in ---------------------------------------------------

def open_terminal(script: str, name: str = "root-harness") -> bool:
    """Open a terminal window that runs `script` (sh on macOS and Linux,
    PowerShell on Windows) and stays open. For the rare step a person must do
    with their own hands: what they type there never passes through us."""
    import tempfile
    folder = Path(tempfile.mkdtemp(prefix="root-harness-"))
    try:
        if windows():
            ps = _powershell()
            if not ps:
                return False
            f = folder / f"{name}.ps1"
            f.write_text(script, encoding="utf-8-sig")
            subprocess.Popen([ps, "-NoLogo", "-NoExit", "-ExecutionPolicy", "Bypass", "-File", str(f)],
                             creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
            return True
        f = folder / f"{name}.command"
        f.write_text("#!/bin/sh\n" + script + "\n", encoding="utf-8")
        f.chmod(0o700)
        if mac():
            return run(["/usr/bin/open", str(f)], stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL, timeout=15).returncode == 0
        for term in (["x-terminal-emulator", "-e"], ["gnome-terminal", "--"], ["konsole", "-e"],
                     ["xfce4-terminal", "-x"], ["kitty"], ["alacritty", "-e"], ["xterm", "-e"]):
            exe = which(term[0])
            if exe:
                popen([exe, *term[1:], "/bin/sh", "-c", f'"{f}"; echo; echo "You can close this window."; read _'],
                      stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL, start_new_session=True)
                return True
        return False
    except (OSError, subprocess.SubprocessError):
        return False


# -- swapping a file in whole ---------------------------------------------------------------

def replace(src, dst, tries: int = 20) -> None:
    """os.replace; on Windows a file another thread or program holds open for a
    moment (a reader, an antivirus) refuses it: try again shortly."""
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if not windows() or i == tries - 1:
                raise
            time.sleep(0.02 * (i + 1))


def atomic_write(path: Path, text: str, private: bool = False) -> None:
    """Write next to it, then swap: a crash never leaves half a file. private:
    readable by you only from the first byte (0600; on Windows the home
    folder's own permissions do that job, the mode is only honoured as
    read-only or not)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.unlink(missing_ok=True)             # O_CREAT keeps the mode of a file already there
    # O_BINARY: without it Windows' C runtime turns each \n into \r\n under Python's back
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(tmp, flags, 0o600 if private else 0o666)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


# -- pictures ---------------------------------------------------------------------------------

def convert_image(src, dest, max_side: int | None = None, quality: int | None = None) -> bool:
    """src to a JPEG at dest, at most max_side pixels a side: sips on macOS,
    ImageMagick elsewhere. False when no converter is there or it failed."""
    if mac() and which("sips"):
        argv = ["sips"] + (["-Z", str(max_side)] if max_side else []) + ["-s", "format", "jpeg"] + \
               (["-s", "formatOptions", str(quality)] if quality else []) + [str(src), "--out", str(dest)]
    else:
        # never a bare `convert` on Windows: that name is the system's disk converter
        im = which("magick") or (None if windows() else which("convert"))
        if not im:
            return False
        argv = [im, f"{src}[0]"] + (["-resize", f"{max_side}x{max_side}>"] if max_side else []) + \
               (["-quality", str(quality)] if quality else []) + [f"jpeg:{dest}"]
    try:
        run(argv, stdin=DEVNULL, capture_output=True, timeout=30, check=True)
        return Path(dest).exists()
    except (OSError, subprocess.SubprocessError):
        return False


def _png_rows(data: bytes):
    """(width, height, bytes per pixel, rows) of an 8-bit RGB/RGBA PNG, or None."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos, idat, head = 8, [], None
    while pos + 8 <= len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if kind == b"IHDR":
            head = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    if not head or head[2] != 8 or head[3] not in (2, 6) or head[6]:
        return None
    w, h, bpp = head[0], head[1], 3 if head[3] == 2 else 4
    raw, stride = zlib.decompress(b"".join(idat)), w * bpp
    rows, prev, i = [], bytearray(stride), 0
    for _ in range(h):
        f, line = raw[i], bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            if f == 1:
                line[x] = (line[x] + a) & 255
            elif f == 2:
                line[x] = (line[x] + b) & 255
            elif f == 3:
                line[x] = (line[x] + ((a + b) >> 1)) & 255
            elif f == 4:
                c = prev[x - bpp] if x >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    return w, h, bpp, rows


def png_to_ico(png: Path, ico: Path, sizes=(256, 48, 32, 16)) -> bool:
    """A Windows .ico (classic 32-bit bitmaps) from a PNG, sampled to the
    nearest pixel: the icon is pixel art. False if the PNG is not plain RGB(A)."""
    try:
        got = _png_rows(Path(png).read_bytes())
    except (OSError, zlib.error, struct.error):
        return False
    if not got:
        return False
    w, h, bpp, rows = got
    images = []
    for s in sizes:
        px = bytearray()
        for y in range(s - 1, -1, -1):                     # bitmaps go bottom-up
            row = rows[y * h // s]
            for x in range(s):
                o = (x * w // s) * bpp
                px += bytes((row[o + 2], row[o + 1], row[o], row[o + 3] if bpp == 4 else 255))
        mask = bytes(((s + 31) // 32) * 4 * s)             # all shown: the alpha channel decides
        head = struct.pack("<IiiHHIIiiII", 40, s, s * 2, 1, 32, 0, len(px) + len(mask), 0, 0, 0, 0)
        images.append((s, head + bytes(px) + mask))
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for s, blob in images:
        out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    try:
        Path(ico).parent.mkdir(parents=True, exist_ok=True)
        Path(ico).write_bytes(out + b"".join(blob for _, blob in images))
        return True
    except OSError:
        return False


# -- the window ---------------------------------------------------------------------------------

def fix_mimetypes() -> None:
    """Windows reads file types from its registry, where .js is sometimes
    text/plain: say what the pages need, the same on every system."""
    for ext, kind in ((".js", "text/javascript"), (".mjs", "text/javascript"), (".css", "text/css"),
                      (".json", "application/json"), (".webmanifest", "application/manifest+json"),
                      (".svg", "image/svg+xml"), (".wasm", "application/wasm")):
        mimetypes.add_type(kind, ext)


def _gtk_ok() -> bool:
    """GTK 3 with WebKit2 importable, the way pywebview asks for them."""
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        try:
            gi.require_version("WebKit2", "4.1")
            gi.require_version("Soup", "3.0")
        except ValueError:
            gi.require_version("WebKit2", "4.0")
            gi.require_version("Soup", "2.4")
        from gi.repository import Gtk, WebKit2      # noqa: F401
        return True
    except Exception:                                # noqa: BLE001  (ImportError, ValueError, a broken install)
        return False


def _qt_ok() -> bool:
    try:
        from qtpy import QtWebEngineWidgets          # noqa: F401  (PyQt6-WebEngine, or PySide6)
        return True
    except Exception:                                # noqa: BLE001
        return False


def pick_gui() -> str | None:
    """The toolkit for pywebview: on Linux GTK if it is importable, else Qt
    (the pip wheels); None elsewhere (Cocoa, WebView2) or when PYWEBVIEW_GUI
    chooses. Asking first spares pywebview's traceback for the one it skips."""
    if not linux() or os.environ.get("PYWEBVIEW_GUI"):
        return None
    if _gtk_ok():
        return "gtk"
    if _qt_ok():
        if os.environ.get("WAYLAND_DISPLAY"):
            os.environ.setdefault("QT_QPA_PLATFORM", "wayland;xcb")    # X11 (XWayland) if Wayland fails
        return "qt"
    return None


NO_TOOLKIT = ("root-harness needs a web view to open its window. Either:\n"
              "  pip install PyQt6 PyQt6-WebEngine qtpy        (no admin rights needed)\n"
              "or the system packages for GTK, e.g.\n"
              "  Ubuntu: sudo apt install python3-gi gir1.2-webkit2-4.1\n"
              "  Fedora: sudo dnf install python3-gobject webkit2gtk4.1\n"
              "(the GTK ones need a virtual environment made with --system-site-packages).")

NO_WEBVIEW2 = """<!doctype html><meta charset="utf-8"><body style="font:15px Segoe UI,sans-serif;padding:32px;background:#11131c;color:#e8e8ee">
<h2>One more piece is needed</h2><p>root-harness shows its window with Microsoft Edge WebView2, which is missing on this computer.</p>
<p>Install the <b>WebView2 Runtime</b> (free, from Microsoft):<br>https://go.microsoft.com/fwlink/p/?LinkId=2124703</p>
<p>then open root-harness again.</p></body>"""


def window_icon(png: Path, home: Path) -> str | None:
    """The window's icon where the toolkit takes one: the PNG for GTK and Qt,
    an .ico made from it for Windows. macOS sets the Dock icon itself."""
    if linux() and Path(png).exists():
        return str(png)
    if windows():
        ico = Path(home) / "icon.ico"
        try:
            fresh = ico.exists() and ico.stat().st_mtime >= Path(png).stat().st_mtime
        except OSError:
            return None
        if fresh or png_to_ico(png, ico):
            return str(ico)
    return None


def claude_home() -> Path:
    """Claude Code's own folder (sessions under projects/): CLAUDE_CONFIG_DIR, or ~/.claude."""
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
