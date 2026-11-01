#!/usr/bin/env bash
# root-harness one-line installer, for macOS and Linux.
#
# Paste this into your terminal (or your Claude Code terminal):
#   curl -fsSL https://raw.githubusercontent.com/redjohn-sudo/root-harness/main/install.sh | bash
#
# It installs root-harness next to your home folder, adds it to your
# Applications (macOS) or your app menu (Linux), and opens it. Your Claude is
# connected through your own logged-in Claude Code: no API key to paste, nothing
# billed to anyone else. Other brains (DeepSeek, Kimi, GLM, Ollama) stay optional
# and use their own keys, entered later in the app.
#
# It never uses sudo. When your system misses something only an administrator
# can add (a recent Python, git, a library the window needs), it stops or warns
# and prints the exact command for your system.
#
# Settings, all optional:
#   ROOT_HARNESS_DIR=<folder>    where to install (default: ~/root-harness)
#   ROOT_HARNESS_NO_LAUNCH=1     install everything, do not open the app
#   ROOT_HARNESS_SKIP_CLAUDE=1   do not look for or install Claude Code
#   ROOT_HARNESS_NO_UPDATE=1     use the copy already in ROOT_HARNESS_DIR as it is
#                                (no clone, no download: for a checkout you work on)
set -euo pipefail

REPO="https://github.com/redjohn-sudo/root-harness"
DEST="${ROOT_HARNESS_DIR:-$HOME/root-harness}"
OS="$(uname -s)"

say()  { printf "\033[0;36m%s\033[0m\n" "$1"; }
warn() { printf "\033[0;33m%s\033[0m\n" "$1"; }
die()  { printf "\033[0;31m%s\033[0m\n" "$1" >&2; exit 1; }
on()   { [ "${1:-0}" = "1" ]; }

case "$OS" in
  Darwin|Linux) ;;
  *) die "This installer is for macOS and Linux. On Windows, in PowerShell:  irm https://raw.githubusercontent.com/redjohn-sudo/root-harness/main/install.ps1 | iex" ;;
esac

# -- Linux: which package manager prints the fix --------------------------------------------
PM=""
DISTRO=""
DISTRO_VERSION=""
if [ "$OS" = "Linux" ]; then
  if [ -r /etc/os-release ]; then
    # shellcheck source=/dev/null
    DISTRO="$(. /etc/os-release && printf "%s %s" "${ID:-}" "${ID_LIKE:-}")"
    # shellcheck source=/dev/null
    DISTRO_VERSION="$(. /etc/os-release && printf "%s" "${VERSION_ID:-}")"
  fi
  case " $DISTRO " in
    *" fedora "*|*" rhel "*|*" centos "*|*" rocky "*|*" almalinux "*) PM=dnf ;;
    *" debian "*|*" ubuntu "*) PM=apt ;;
    *" arch "*|*" manjaro "*) PM=pacman ;;
    *suse*) PM=zypper ;;
  esac
  if [ -z "$PM" ]; then
    if command -v dnf >/dev/null 2>&1; then PM=dnf
    elif command -v apt-get >/dev/null 2>&1; then PM=apt
    elif command -v pacman >/dev/null 2>&1; then PM=pacman
    elif command -v zypper >/dev/null 2>&1; then PM=zypper
    fi
  fi
fi

# The one command that installs these packages here (printed, never run).
pkg_cmd() {
  case "$PM" in
    apt)    printf "sudo apt-get update && sudo apt-get install -y %s" "$*" ;;
    dnf)    printf "sudo dnf install -y %s" "$*" ;;
    pacman) printf "sudo pacman -S --needed %s" "$*" ;;
    zypper) printf "sudo zypper install -y %s" "$*" ;;
    *)      printf "install with your package manager: %s" "$*" ;;
  esac
}

# A package apt can install here (Ubuntu 24.04 renamed some with a t64 suffix).
apt_name() {
  if command -v apt-cache >/dev/null 2>&1 && ! apt-cache show "$1" >/dev/null 2>&1 \
      && apt-cache show "${1}t64" >/dev/null 2>&1; then
    printf "%st64" "$1"
  else
    printf "%s" "$1"
  fi
}

MISSING=()          # system packages without which nothing can be installed
FIX_NOTES=()        # extra lines printed with the fix

# -- 1. git ---------------------------------------------------------------------------------
# macOS: /usr/bin/git is a stub until the Command Line Tools are installed, so run it.
if ! git --version >/dev/null 2>&1; then
  if [ "$OS" = "Darwin" ]; then
    FIX_NOTES+=("git is missing. Install Apple's Command Line Tools:  xcode-select --install   (or: brew install git)")
  else
    MISSING+=(git)
  fi
fi

# -- 2. A Python 3.11 or newer --------------------------------------------------------------
# macOS ships 3.9, too old: look where Homebrew and python.org put a recent one too.
py_ok() { "$1" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)' >/dev/null 2>&1; }
PY=""
CANDIDATES=()
for v in 3.12 3.13 3.11 3.14; do
  if command -v "python$v" >/dev/null 2>&1; then CANDIDATES+=("$(command -v "python$v")"); fi
  if [ "$OS" = "Darwin" ]; then
    CANDIDATES+=("/opt/homebrew/bin/python$v" "/usr/local/bin/python$v"
                 "/Library/Frameworks/Python.framework/Versions/$v/bin/python$v")
  fi
done
if command -v python3 >/dev/null 2>&1; then
  P3="$(command -v python3)"
  # the macOS stub opens an install dialog and is 3.9 anyway
  if [ "$OS" != "Darwin" ] || [ "$P3" != "/usr/bin/python3" ]; then CANDIDATES+=("$P3"); fi
fi
for cand in ${CANDIDATES[@]+"${CANDIDATES[@]}"}; do
  if [ -x "$cand" ] && py_ok "$cand"; then PY="$cand"; break; fi
done

if [ -z "$PY" ]; then
  if [ "$OS" = "Darwin" ]; then
    FIX_NOTES+=("root-harness needs Python 3.11 or newer (macOS ships 3.9). Install one:"
                "  brew install python@3.12      (Homebrew, https://brew.sh)"
                "  or the installer from https://www.python.org/downloads/macos/")
  else
    case "$PM" in
      apt)
        PYPKG=""
        for v in 3.12 3.13 3.11; do
          if command -v apt-cache >/dev/null 2>&1 && apt-cache show "python$v-venv" >/dev/null 2>&1; then PYPKG="python$v python$v-venv"; break; fi
        done
        if [ -n "$PYPKG" ]; then
          # shellcheck disable=SC2206
          MISSING+=($PYPKG)
        elif [[ " $DISTRO " == *" ubuntu "* ]]; then
          FIX_NOTES+=("root-harness needs Python 3.11 or newer; Ubuntu $DISTRO_VERSION has an older one. Add it from the deadsnakes archive:"
                      "  sudo add-apt-repository -y ppa:deadsnakes/ppa && sudo apt-get update && sudo apt-get install -y python3.12 python3.12-venv")
        else
          FIX_NOTES+=("root-harness needs Python 3.11 or newer, and this system offers none. Debian 12 or newer has it; or install one with pyenv (https://github.com/pyenv/pyenv).")
        fi ;;
      dnf)    MISSING+=(python3.12) ;;
      pacman) MISSING+=(python) ;;
      zypper) MISSING+=(python312) ;;
      *)      FIX_NOTES+=("root-harness needs Python 3.11 or newer. Install it with your package manager, then run this again.") ;;
    esac
  fi
elif [ "$OS" = "Linux" ] && ! "$PY" -c 'import venv, ensurepip' >/dev/null 2>&1; then
  # Debian and Ubuntu ship venv separately
  PYV="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  if [ "$PM" = "apt" ]; then MISSING+=("python$PYV-venv")
  else FIX_NOTES+=("$PY cannot make a virtual environment: install your system's venv package for Python $PYV.")
  fi
fi

if [ "${#MISSING[@]}" -gt 0 ] || [ "${#FIX_NOTES[@]}" -gt 0 ]; then
  printf "\033[0;31m%s\033[0m\n" "root-harness cannot be installed yet: a few things are missing on this computer." >&2
  for line in ${FIX_NOTES[@]+"${FIX_NOTES[@]}"}; do printf "%s\n" "$line" >&2; done
  if [ "${#MISSING[@]}" -gt 0 ]; then
    printf "Install them with this command (it asks for your password):\n  %s\n" "$(pkg_cmd "${MISSING[@]}")" >&2
  fi
  printf "Then run the installer again.\n" >&2
  exit 1
fi
say "Using $("$PY" --version) ($PY)"

# -- 3. Claude Code is what connects their Claude, through the SDK, with no key -------------
#    If it is missing, install it for them (the official installer). Logging in
#    is a browser step they do themselves: it cannot run inside a piped script.
export PATH="$HOME/.local/bin:$PATH"
NEED_LOGIN=0
if on "${ROOT_HARNESS_SKIP_CLAUDE:-0}"; then
  say "Skipping Claude Code (ROOT_HARNESS_SKIP_CLAUDE=1)."
elif command -v claude >/dev/null 2>&1; then
  say "Claude Code found: your Claude will be connected through your own login."
else
  say "Claude Code was not found. Installing it (this is what connects your Claude)..."
  if curl -fsSL https://claude.ai/install.sh | bash; then
    hash -r 2>/dev/null || true
    if command -v claude >/dev/null 2>&1; then
      say "Claude Code installed."
      NEED_LOGIN=1
    else
      warn "Claude Code was installed but is not on your PATH yet. Open a new"
      warn "terminal, run 'claude' once to log in, then start root-harness."
      NEED_LOGIN=1
    fi
  else
    warn "Could not install Claude Code automatically. Install it yourself from"
    warn "https://claude.com/claude-code , run 'claude' once to log in, then start"
    warn "root-harness. It will still install now; its Claude brain waits for login."
  fi
fi

# -- 4. Clone, or update an existing copy ---------------------------------------------------
if on "${ROOT_HARNESS_NO_UPDATE:-0}"; then
  [ -f "$DEST/app.py" ] || die "ROOT_HARNESS_NO_UPDATE=1 needs a root-harness copy in $DEST, and there is none."
  say "Using the copy in $DEST as it is (ROOT_HARNESS_NO_UPDATE=1)."
elif [ -d "$DEST/.git" ]; then
  say "Updating existing copy in $DEST"
  git -C "$DEST" remote set-url origin "$REPO"
  git -C "$DEST" fetch --quiet --depth 1 origin main || die "Could not reach $REPO. Check your internet and run this again."
  if ! git -C "$DEST" merge --quiet --ff-only FETCH_HEAD 2>/dev/null; then
    # an older copy (the history was rewritten on 30/10), or local edits in the way:
    # keep the edits aside, then take the published version as it is
    if [ -n "$(git -C "$DEST" status --porcelain --untracked-files=no)" ]; then
      BACKUP="$DEST.backup-$(date +%Y%m%d-%H%M%S)"
      mkdir -p "$BACKUP"
      git -C "$DEST" diff HEAD > "$BACKUP/local-changes.patch"
      git -C "$DEST" diff HEAD --name-only | while IFS= read -r f; do
        if [ -e "$DEST/$f" ]; then mkdir -p "$BACKUP/$(dirname "$f")"; cp -R "$DEST/$f" "$BACKUP/$f"; fi
      done
      warn "Your local edits to root-harness's files are saved in $BACKUP"
    fi
    git -C "$DEST" reset --quiet --hard FETCH_HEAD
    say "Your copy now matches the published root-harness. Your account and memory"
    say "(~/.root-harness) live outside this folder: they are not touched."
  fi
else
  [ -e "$DEST" ] && die "$DEST already exists and is not a root-harness checkout. Set ROOT_HARNESS_DIR to another path and retry."
  say "Cloning into $DEST"
  git clone --quiet --depth 1 "$REPO" "$DEST" || die "Could not download $REPO. Check your internet and run this again."
fi
cd "$DEST"
DEST="$(pwd -P)"        # an absolute path, for the launchers

# -- 5. A private virtual environment and the dependencies ----------------------------------
# A venv left by an older or removed Python is rebuilt instead of failing later.
if [ -e .venv ] && ! { [ -x .venv/bin/python ] && py_ok .venv/bin/python; }; then
  warn "The old .venv in $DEST no longer works with a recent Python: rebuilding it."
  rm -rf "${DEST:?}/.venv"
fi
say "Installing dependencies (this can take a minute)..."
"$PY" -m venv .venv
.venv/bin/python -m pip install --quiet --disable-pip-version-check --upgrade pip
.venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt \
  || die "Installing the dependencies failed (see above). Check your internet and run this again."

# -- 6. Linux: the system libraries the window (Qt WebEngine) loads --------------------------
# pip brings Qt itself; these few come with every desktop but can miss on a minimal
# install. Each soname with its package on apt | dnf | pacman | zypper.
QT_LIBS="
libxcb-cursor.so.0|libxcb-cursor0|xcb-util-cursor|xcb-util-cursor|libxcb-cursor0
libxcb-icccm.so.4|libxcb-icccm4|xcb-util-wm|xcb-util-wm|libxcb-icccm4
libxcb-image.so.0|libxcb-image0|xcb-util-image|xcb-util-image|libxcb-image0
libxcb-keysyms.so.1|libxcb-keysyms1|xcb-util-keysyms|xcb-util-keysyms|libxcb-keysyms1
libxcb-render-util.so.0|libxcb-render-util0|xcb-util-renderutil|xcb-util-renderutil|libxcb-render-util0
libxcb-util.so.1|libxcb-util1|xcb-util|xcb-util|libxcb-util1
libxcb-randr.so.0|libxcb-randr0|libxcb|libxcb|libxcb-randr0
libxcb-shape.so.0|libxcb-shape0|libxcb|libxcb|libxcb-shape0
libxcb-xkb.so.1|libxcb-xkb1|libxcb|libxcb|libxcb-xkb1
libxcb-xfixes.so.0|libxcb-xfixes0|libxcb|libxcb|libxcb-xfixes0
libxcb-sync.so.1|libxcb-sync1|libxcb|libxcb|libxcb-sync1
libxcb-shm.so.0|libxcb-shm0|libxcb|libxcb|libxcb-shm0
libxcb-render.so.0|libxcb-render0|libxcb|libxcb|libxcb-render0
libxcb-glx.so.0|libxcb-glx0|libxcb|libxcb|libxcb-glx0
libxcb-dri3.so.0|libxcb-dri3-0|libxcb|libxcb|libxcb-dri3-0
libxcb.so.1|libxcb1|libxcb|libxcb|libxcb1
libxkbcommon.so.0|libxkbcommon0|libxkbcommon|libxkbcommon|libxkbcommon0
libxkbcommon-x11.so.0|libxkbcommon-x11-0|libxkbcommon-x11|libxkbcommon-x11|libxkbcommon-x11-0
libxkbfile.so.1|libxkbfile1|libxkbfile|libxkbfile|libxkbfile1
libX11.so.6|libx11-6|libX11|libx11|libX11-6
libX11-xcb.so.1|libx11-xcb1|libX11-xcb|libx11|libX11-xcb1
libXcomposite.so.1|libxcomposite1|libXcomposite|libxcomposite|libXcomposite1
libXdamage.so.1|libxdamage1|libXdamage|libxdamage|libXdamage1
libXext.so.6|libxext6|libXext|libxext|libXext6
libXfixes.so.3|libxfixes3|libXfixes|libxfixes|libXfixes3
libXi.so.6|libxi6|libXi|libxi|libXi6
libXrandr.so.2|libxrandr2|libXrandr|libxrandr|libXrandr2
libXrender.so.1|libxrender1|libXrender|libxrender|libXrender1
libXtst.so.6|libxtst6|libXtst|libxtst|libXtst6
libxshmfence.so.1|libxshmfence1|libxshmfence|libxshmfence|libxshmfence1
libEGL.so.1|libegl1|libglvnd-egl|libglvnd|libEGL1
libGL.so.1|libgl1|libglvnd-glx|libglvnd|libGL1
libgbm.so.1|libgbm1|mesa-libgbm|mesa|libgbm1
libdrm.so.2|libdrm2|libdrm|libdrm|libdrm2
libnss3.so|libnss3|nss|nss|mozilla-nss
libnspr4.so|libnspr4|nspr|nspr|mozilla-nspr
libasound.so.2|libasound2|alsa-lib|alsa-lib|libasound2
libdbus-1.so.3|libdbus-1-3|dbus-libs|dbus|libdbus-1-3
libfontconfig.so.1|libfontconfig1|fontconfig|fontconfig|libfontconfig1
libfreetype.so.6|libfreetype6|freetype|freetype2|libfreetype6
libglib-2.0.so.0|libglib2.0-0|glib2|glib2|libglib-2_0-0
libgssapi_krb5.so.2|libgssapi-krb5-2|krb5-libs|krb5|krb5
"

LDCACHE=""
lib_present() {
  local so="$1" d
  if [ -n "$LDCACHE" ]; then
    printf "%s\n" "$LDCACHE" | grep -qxF "$so ("
    return
  fi
  for d in /usr/lib64 /usr/lib /lib64 /lib "/usr/lib/$(uname -m)-linux-gnu" "/lib/$(uname -m)-linux-gnu"; do
    [ -e "$d/$so" ] && return 0
  done
  return 1
}

QT_MISSING=()
if [ "$OS" = "Linux" ] && .venv/bin/python -c 'import importlib.util, sys; sys.exit(0 if importlib.util.find_spec("PyQt6") else 1)' 2>/dev/null; then
  LDCONFIG="$(command -v ldconfig 2>/dev/null || true)"
  [ -z "$LDCONFIG" ] && [ -x /sbin/ldconfig ] && LDCONFIG=/sbin/ldconfig
  [ -z "$LDCONFIG" ] && [ -x /usr/sbin/ldconfig ] && LDCONFIG=/usr/sbin/ldconfig
  if [ -n "$LDCONFIG" ]; then
    ARCHTAG=""
    case "$(uname -m)" in x86_64) ARCHTAG="x86-64" ;; aarch64) ARCHTAG="AArch64" ;; esac
    LDCACHE="$("$LDCONFIG" -p 2>/dev/null | { if [ -n "$ARCHTAG" ]; then grep -F "$ARCHTAG"; else cat; fi; } | awk '{print $1" ("}' || true)"
  fi
  SEEN=" "
  # a library Qt itself names when it fails to load (more exact than any list)
  PROBE="$(QT_QPA_PLATFORM=offscreen .venv/bin/python -c 'from PyQt6 import QtWebEngineWidgets' 2>&1 || true)"
  EXTRA="$(printf "%s\n" "$PROBE" | grep -oE 'lib[A-Za-z0-9_.+-]+\.so(\.[0-9]+)*: cannot open' | sed 's/: cannot open//' | head -n 3 || true)"
  while IFS='|' read -r so p_apt p_dnf p_pacman p_zypper; do
    [ -n "$so" ] || continue
    if ! lib_present "$so" || printf "%s\n" "$EXTRA" | grep -qxF "$so"; then
      case "$PM" in
        apt) pkg="$(apt_name "$p_apt")" ;; dnf) pkg="$p_dnf" ;; pacman) pkg="$p_pacman" ;; zypper) pkg="$p_zypper" ;; *) pkg="$so" ;;
      esac
      case "$SEEN" in *" $pkg "*) ;; *) QT_MISSING+=("$pkg"); SEEN="$SEEN$pkg " ;; esac
    fi
  done <<< "$QT_LIBS"
  QT_UNKNOWN=()
  for so in $EXTRA; do      # one the table does not know: name the file itself
    if ! printf "%s\n" "$QT_LIBS" | grep -qF "$so|"; then QT_UNKNOWN+=("$so"); fi
  done
  if [ "${#QT_MISSING[@]}" -gt 0 ] || [ "${#QT_UNKNOWN[@]}" -gt 0 ]; then
    warn ""
    warn "The window needs a few system libraries this computer does not have yet."
    if [ "${#QT_MISSING[@]}" -gt 0 ]; then
      warn "Install them with this command (it asks for your password):"
      warn "  $(pkg_cmd "${QT_MISSING[@]}")"
    fi
    for so in ${QT_UNKNOWN[@]+"${QT_UNKNOWN[@]}"}; do
      case "$PM" in
        dnf)    hint="dnf provides '*/$so'" ;;
        apt)    hint="apt-file search $so" ;;
        pacman) hint="pacman -F $so" ;;
        zypper) hint="zypper search --provides $so" ;;
        *)      hint="your package manager's search" ;;
      esac
      warn "  and the package that provides $so (find it with: $hint)"
      QT_MISSING+=("$so")
    done
  fi
fi

# -- 7. A launcher: Applications (macOS) or the app menu (Linux) ----------------------------
sq() { printf "'%s'" "$(printf "%s" "$1" | sed "s/'/'\\\\''/g")"; }   # quoted for sh

# The script the launcher runs: from the Dock or an app menu there is no terminal PATH,
# and the app looks for claude, gh, codex and ollama on it.
write_launcher() {   # <path> <log file>
  cat > "$1" <<EOF
#!/bin/sh
# Starts root-harness. Written by install.sh (running it again rewrites this file).
DEST=$(sq "$DEST")
LOG=$(sq "$2")
if [ ! -t 1 ]; then
  if [ -n "\${SHELL:-}" ]; then
    P="\$("\$SHELL" -l -c 'printf "%s" "\$PATH"' 2>/dev/null </dev/null || true)"
    case "\$P" in */*) PATH="\$P" ;; esac
  fi
  mkdir -p "\$(dirname "\$LOG")" && exec >"\$LOG" 2>&1
fi
for d in "\$HOME/.local/bin" /opt/homebrew/bin /usr/local/bin; do
  case ":\$PATH:" in *":\$d:"*) ;; *) [ -d "\$d" ] && PATH="\$d:\$PATH" ;; esac
done
export PATH
cd "\$DEST" || exit 1
exec "\$DEST/.venv/bin/python" "\$DEST/app.py" "\$@"
EOF
  chmod 755 "$1"
}

# a value for a .desktop file's Exec= line (quoted per the Desktop Entry spec)
desktop_quote() {
  local s="$1"
  case "$s" in *[!A-Za-z0-9/._+-]*) ;; *) printf "%s" "$s"; return ;; esac
  s="${s//\\/\\\\\\\\}"; s="${s//\"/\\\\\"}"; s="${s//\`/\\\\\`}"; s="${s//\$/\\\\\$}"; s="${s//%/%%}"
  printf '"%s"' "$s"
}

ICON_SRC="$DEST/mobile/dist/icon-512.png"
LAUNCHED_FROM=""
if [ "$OS" = "Darwin" ]; then
  APP="$HOME/Applications/root-harness.app"
  if mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" 2>/dev/null; then
    cat > "$APP/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>root-harness</string>
  <key>CFBundleDisplayName</key><string>root-harness</string>
  <key>CFBundleIdentifier</key><string>io.github.redjohn-sudo.root-harness</string>
  <key>CFBundleExecutable</key><string>root-harness</string>
  <key>CFBundleIconFile</key><string>root-harness</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
EOF
    write_launcher "$APP/Contents/MacOS/root-harness" "$HOME/Library/Logs/root-harness.log"
    if [ -f "$ICON_SRC" ] && command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
      ICONSET="$(mktemp -d)/root-harness.iconset"
      mkdir -p "$ICONSET"
      for s in 16 32 128 256 512; do
        sips -z "$s" "$s" "$ICON_SRC" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null 2>&1 || true
        d=$((s * 2))
        [ "$d" -le 512 ] && { sips -z "$d" "$d" "$ICON_SRC" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null 2>&1 || true; }
      done
      iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/root-harness.icns" 2>/dev/null \
        || warn "Could not make the app icon (the app still works)."
      rm -rf "${ICONSET:?}"
      rmdir "$(dirname "$ICONSET")" 2>/dev/null || true
    fi
    touch "$APP"
    LSREG=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
    [ -x "$LSREG" ] && "$LSREG" -f "$APP" >/dev/null 2>&1 || true
    LAUNCHED_FROM="root-harness from your Applications folder or Spotlight"
  else
    warn "Could not add root-harness to ~/Applications (the app still works)."
  fi
else
  DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
  BIN="$HOME/.local/bin/root-harness"
  ICON="$DATA/icons/hicolor/512x512/apps/root-harness.png"
  if mkdir -p "$(dirname "$BIN")" "$DATA/applications" "$(dirname "$ICON")" 2>/dev/null; then
    write_launcher "$BIN" "${XDG_STATE_HOME:-$HOME/.local/state}/root-harness/launch.log"
    [ -f "$ICON_SRC" ] && cp "$ICON_SRC" "$ICON"
    {
      printf "[Desktop Entry]\n"
      printf "Type=Application\n"
      printf "Version=1.0\n"
      printf "Name=root-harness\n"
      printf "GenericName=AI agents\n"
      printf "Comment=Your agents, your friends and the network, in one window\n"
      printf "Exec=%s\n" "$(desktop_quote "$BIN")"
      printf "Icon=%s\n" "$ICON"
      printf "Terminal=false\n"
      printf "Categories=Development;\n"
      printf "StartupNotify=true\n"
    } > "$DATA/applications/root-harness.desktop"
    chmod 755 "$DATA/applications/root-harness.desktop"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$DATA/applications" 2>/dev/null || true
    LAUNCHED_FROM="root-harness from your app menu (or run $BIN)"
  else
    warn "Could not add root-harness to your app menu (the app still works)."
  fi
fi

# -- 8. Open it, unless they still need to log in to the Claude Code we just installed ------
#    (its Claude brain stays dark until that one browser step is done), the window still
#    misses a library, or there is no screen (an SSH session, a CI machine).
START_CMD="cd \"$DEST\" && .venv/bin/python app.py"
OPEN_HINT="${LAUNCHED_FROM:-it from a terminal: $START_CMD}"
say ""
if [ "$NEED_LOGIN" = "1" ]; then
  say "Almost there. Two steps, once:"
  say "  1. Log in to Claude Code:   claude          (then press Ctrl-C after login)"
  say "  2. Open $OPEN_HINT"
  say ""
  say "Claude Code needs a Pro, Max, Team or Console account; the free plan does not include it."
  exit 0
fi
if on "${ROOT_HARNESS_NO_LAUNCH:-0}"; then
  say "Installed in $DEST (not opened: ROOT_HARNESS_NO_LAUNCH=1)."
  say "Open $OPEN_HINT"
  exit 0
fi
if [ "${#QT_MISSING[@]}" -gt 0 ]; then
  warn "Installed in $DEST. Install the libraries above, then open $OPEN_HINT"
  exit 0
fi
if [ "$OS" = "Linux" ] && [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
  say "Installed in $DEST. This session has no screen (SSH?): from your desktop, open $OPEN_HINT"
  exit 0
fi
say "Done. Opening root-harness."
say "Next time, open $OPEN_HINT"
exec .venv/bin/python app.py </dev/null
