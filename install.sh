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
#    If it is missing, install it for them (the official installer). Logging in
#    is a browser step they do themselves: it cannot run inside a piped script.
export PATH="$HOME/.local/bin:$PATH"
NEED_LOGIN=0
if command -v claude >/dev/null 2>&1; then
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

# 5. Open it, unless they still need to log in to the Claude Code we just
#    installed (its Claude brain stays dark until that one browser step is done).
say ""
if [ "$NEED_LOGIN" = "1" ]; then
  say "Almost there. Two steps, once:"
  say "  1. Log in to Claude Code:   claude          (then press Ctrl-C after login)"
  say "  2. Start root-harness:      cd \"$DEST\" && .venv/bin/python app.py"
  say ""
  say "Claude Code needs a Pro, Max, Team or Console account; the free plan does not include it."
  exit 0
fi
say "Done. Opening root-harness."
say "Next time, start it with:  cd \"$DEST\" && .venv/bin/python app.py"
exec .venv/bin/python app.py
