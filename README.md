<p align="center"><img src="ui-src/assets/root-head.svg" width="96" alt="Root"></p>

# root-harness

**root-harness, powered by Claude.** All your AI agents in one window, the same
on your computer and on your phone, and a sealed way to hand a conversation to a
friend so their own agent continues it.

Free and open source (AGPL-3.0). No server of ours: your account, your memory
and your messages live on your devices, and travel sealed.

## What it does

- **Every agent, one place.** Claude Agent (the Claude Code installed on your
  computer, signed in with your own account), Codex, DeepSeek, Kimi, GLM,
  Ollama. Every model, effort and slash command; a permission card before
  anything risky; every step kept in the conversation, to read back or continue.
- **The same on your phone.** One account, a pseudo and a password. Your
  conversations, folders, friends and keys follow you, sealed. With your
  computer on, the phone drives its agents.
- **Share with a friend, sealed.** Add a friend with their ID, make a group, send
  a conversation: they read it, or continue it with their own agent. Relays see
  neither the text nor who talks to whom.
- **Vibe code with your computer off (beta).** From your phone, pick one of your
  GitHub repositories and describe an idea: Claude Code builds it on GitHub's
  machines with your plan and opens a pull request you review.

Also in the box, off by default until there are people to use it with: a public
page for your `@name`, and a public network (posts, communities, badges) on
Nostr relays. Turn it on in Settings, *public network*. Seven languages.

## Install

One command for your system. It needs nothing but a terminal, and the installer
itself never asks for administrator rights.

**macOS** (Terminal) and **Linux** (any terminal):

```bash
curl -fsSL https://raw.githubusercontent.com/redjohn-sudo/root-harness/main/install.sh | bash
```

**Windows 10 and 11** (PowerShell, from the Start menu):

```powershell
irm https://raw.githubusercontent.com/redjohn-sudo/root-harness/main/install.ps1 | iex
```

What the installer does:

1. Finds a **Python 3.11 or newer** and **git**. On Windows it installs them for
   your user with `winget` when they are missing. On macOS and Linux it never
   uses `sudo`: if one is missing, it stops and prints the exact command for
   your system (Homebrew, `apt`, `dnf`, `pacman` or `zypper`).
2. Installs [Claude Code](https://claude.com/claude-code) with its official
   installer when it is not there yet. Your Claude is connected through your own
   logged-in Claude Code: no API key to paste. Run `claude` once to sign in
   (a Pro, Max, Team or Console plan).
3. Downloads root-harness to `~/root-harness` (or updates it: local edits are
   kept aside in a backup folder), with its own private Python environment in
   `~/root-harness/.venv`.
4. On Linux, checks the few system libraries the window needs and prints the
   one command that adds the missing ones.
5. Adds root-harness where you open apps: `~/Applications` and Spotlight on
   macOS, the app menu on Linux (and `~/.local/bin/root-harness`), the Start
   menu and the desktop on Windows.
6. Opens it.

Your account, your memory and your settings live in `~/.root-harness`, outside
the install folder: installing again or updating never touches them.

| You have | Needed |
|---|---|
| macOS 11 or newer | Python 3.11+ (macOS ships 3.9: `brew install python@3.12` or [python.org](https://www.python.org/downloads/macos/)), git (`xcode-select --install`) |
| Linux with a desktop (GNOME, KDE...) | Python 3.11+, git, a few X11/Qt libraries: the installer tells you which |
| Windows 10 (1809+) or 11 | nothing: Python and Git come through `winget`; the window uses Microsoft Edge WebView2, built into Windows 11 |

Options, set before the command (on Windows: `$env:NAME = '1'` first):
`ROOT_HARNESS_DIR` (another install folder), `ROOT_HARNESS_NO_LAUNCH=1`
(install without opening), `ROOT_HARNESS_SKIP_CLAUDE=1` (leave Claude Code
alone), `ROOT_HARNESS_NO_UPDATE=1` (use the copy already in
`ROOT_HARNESS_DIR` as it is).

Or by hand, with Python 3.11 or newer:

```bash
git clone https://github.com/redjohn-sudo/root-harness
cd root-harness
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt   # Windows: .venv\Scripts\pip
.venv/bin/python app.py                                                # Windows: .venv\Scripts\python app.py
```

Other agents than Claude need their key (typed once in the app) or a local
Ollama.

**Tests:** `pytest -q` runs the fast tests; `python tests/smoke_gui.py` opens
the real window for a few seconds and checks it answers (on a Linux machine
without a screen: `xvfb-run -a python tests/smoke_gui.py`). Every push runs
both on macOS, Linux and Windows, after installing with the scripts above.

**On your phone:** in the app, Settings, *Use from my phone*: open the address
it shows in Safari (type `http://` in full), sign in, then *Add to Home Screen*.
With your computer on, the phone drives its agents; computer off, the phone
still has your friends, your memory and vibe code.

**Vibe code:** Settings, *Vibe code*, *Create my workshop* (a private
`root-harness-runner` repository), then two buttons, once:

- *Connect* your GitHub: one click. The key goes from `gh` straight into `gh`;
  root-harness never reads it.
- *Open the sign-in* for your Claude plan: a terminal window opens, you sign in
  with the official `claude setup-token`, and paste the key it shows to `gh`
  yourself. root-harness never handles your Claude sign-in.

Then turn on *GitHub on my phone* to vibe code from the phone.

## How it is made

| Part | Where |
|---|---|
| The interface, one source for computer and phone | `ui-src/` (`npm run build`) |
| Agents (Claude Code via the Agent SDK, Codex app server, API keys) | `rootharness/brains.py`, `bridge_*.py` |
| Account (NIP-49 locked identity) and sync (sealed pieces, NIP-44 / NIP-78) | `rootharness/account.py`, `sync.py` |
| Friends and groups (NIP-17 / NIP-59 sealed messages) | `rootharness/channels.py` |
| The phone as a remote (sealed orders to yourself) | `rootharness/remote.py` |
| Vibe code (one workshop repository, Claude Code GitHub Action) | `rootharness/vibe.py`, `rootharness/github/` |
| The network (public Nostr events: profile, posts, reactions, NIP-58 badges, communities; NIP-96 media) | `rootharness/network.py`, `ui-src/social-net.js`, `ui-src/social.js` |

root-harness is an independent project, not made or endorsed by Anthropic. It
never handles your Claude sign-in: you sign in to the official Claude Code
yourself, and each person uses their own account or API key.

Honest limits: free relays promise no storage and may rate-limit; they see
your IP and when you connect. A stolen identity key would open past messages.
What you post on the network is public, signed with your key and kept by
relays you do not control: it may stay even after you delete it. An @ goes to
whoever claimed it first; with no central server, a claim's date is the one its
author signed, so the `pseudo#code` ID remains the one nobody can copy.
The GitHub key you give your vibe-code workshop can do what your `gh` sign-in can, in all your
repositories, and Claude Code runs there with a shell: only point it at code you
trust, or give the workshop a fine-grained token limited to the repositories you
choose (`gh secret set RH_GITHUB_TOKEN`).
Claude Code sessions stay on the computer that ran them. Vibe code is not live
(a GitHub machine starts in about a minute) and uses your GitHub Actions minutes
and your Claude plan.

## License

root-harness is free software under the [GNU AGPL v3](LICENSE). Use it, study
it, change it, share it. If you change it and offer it to others (even as an
online service), you share your changes under the same license: nobody can lock
it up. The name root-harness and Root's pixel head are the author's own work.

The photos behind the sign-up screen come from Unsplash, under the Unsplash License:
[Mạnh Ngô](https://unsplash.com/photos/7X-Cw-5WN9Q),
[Seongjin Park](https://unsplash.com/photos/Y-95B4hj9Bk),
[Dina Badamshina](https://unsplash.com/photos/zHT9jQZ6iTs),
[jötâkå](https://unsplash.com/photos/rdm0IzLB1uo),
[zhenzhong liu](https://unsplash.com/photos/WYxiXeupIY4) and
[Sinem Tunalı](https://unsplash.com/photos/tJYDh6kX0IM).

Copyright (C) 2026 Vincent Roumane
