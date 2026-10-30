#!/usr/bin/env bash
# root-harness one-line installer.
#
# Paste this into your terminal (or your Claude Code terminal):
#   curl -fsSL https://raw.githubusercontent.com/redjohn-sudo/root-harness/main/install.sh | bash
#
# It installs root-harness next to your home folder and opens it. Your Claude is
# connected through your own logged-in Claude Code: no API key to paste, nothing
# billed to anyone else. Other brains (DeepSeek, Kimi, GLM, Ollama) stay optional
# and use their own keys, entered later in the app.
set -euo pipefail

REPO="https://github.com/redjohn-sudo/root-harness"
DEST="${ROOT_HARNESS_DIR:-$HOME/root-harness}"

say()  { printf "\033[0;36m%s\033[0m\n" "$1"; }
warn() { printf "\033[0;33m%s\033[0m\n" "$1"; }
die()  { printf "\033[0;31m%s\033[0m\n" "$1" >&2; exit 1; }

# 1. A Python 3.11 or newer. macOS ships 3.9, too old.
PY=""
for cand in python3.13 python3.12 python3.11 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    if "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,11) else 1)' 2>/dev/null; then
      PY="$cand"; break
    fi
  fi
done
[ -n "$PY" ] || die "root-harness needs Python 3.11 or newer. Install it (macOS: brew install python@3.12) and run this again."
say "Using $($PY --version)"

# 2. Claude Code is what connects their Claude, through the SDK, with no key.
if command -v claude >/dev/null 2>&1; then
  say "Claude Code found: your Claude will be connected through your own login."
else
  warn "Claude Code was not found on this machine."
  warn "root-harness will still install, but its Claude brain needs Claude Code"
  warn "installed and logged in. Get it at https://claude.com/claude-code , run"
  warn "'claude' once to log in, then start root-harness."
fi

# 3. Clone, or update an existing copy.
if [ -d "$DEST/.git" ]; then
  say "Updating existing copy in $DEST"
  git -C "$DEST" pull --ff-only
else
  [ -e "$DEST" ] && die "$DEST already exists and is not a root-harness checkout. Set ROOT_HARNESS_DIR to another path and retry."
  say "Cloning into $DEST"
  git clone --depth 1 "$REPO" "$DEST"
fi
cd "$DEST"

# 4. A private virtual environment and the dependencies.
say "Installing dependencies (this can take a minute)..."
"$PY" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt

# 5. Open it.
say ""
say "Done. Opening root-harness."
say "Next time, start it with:  cd \"$DEST\" && .venv/bin/python app.py"
exec .venv/bin/python app.py
