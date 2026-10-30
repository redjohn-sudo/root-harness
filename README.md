<p align="center"><img src="ui-src/assets/root-head.svg" width="96" alt="Root"></p>

# root-harness

**root-harness, powered by Claude.** One simple place for all your AI agents,
the same on your computer and on your phone. Talk to them, let them work, vibe code on GitHub from anywhere, and share
what they did with your friends, sealed end to end.

Free and open source (AGPL-3.0). No server of ours: your account, your memory
and your messages live on your devices, and travel sealed.

## What you can do

- **Work with your agents.** Claude Agent (it runs the Claude Code installed on
  your computer, signed in with your own account), Codex, DeepSeek, Kimi, GLM,
  Ollama... Every model, effort and slash
  command; permission cards before anything risky; images; Esc to stop.
- **Vibe code from your phone, computer off.** Have an idea outside? Pick any of
  your GitHub repositories (or a new one), describe it: Claude Agent builds it on
  GitHub's machines with your plan and opens a pull request you review.
- **Friends and groups.** Add friends with their ID, make groups, talk,
  sealed end to end (relays see neither the text nor who talks to whom).
- **Share your agents' work.** Send a conversation to a friend or a group; they
  read it, or continue it with their own agent.
- **One account, every device.** A pseudo and a password. Sign in on another
  computer or your phone: your conversations, folders, friends, background and
  keys come with you, sealed.
- **The network.** A page anyone can see (your projects, hackathons, what is in
  progress, "looking for a job"), a feed of what people build with their agents,
  communities, replies, reposts, badges to earn and to pin. Your agent writes
  the post about the work you just did; you decide, or let it post by itself.
  Everything on the network is public and lives on the relays: no server of ours.
- **Your @.** Take a name (`@yourname`): the first to claim it keeps it,
  and nobody else can show it. Your `pseudo#code` ID still works everywhere.
- **Seven languages.** Deutsch, English, 中文, Español, Français, 日本語, Português.

## Start

One line, from your terminal (or your Claude Code terminal). It picks a recent
Python, installs root-harness, and opens it. Your Claude is connected through
your own logged-in Claude Code: no API key to paste. If you do not have Claude
Code yet, the installer sets it up and shows you the one login step.

```bash
curl -fsSL https://raw.githubusercontent.com/redjohn-sudo/root-harness/main/install.sh | bash
```

Or by hand. Needs **Python 3.11 or newer** (on macOS the built-in `python3` is
3.9: too old, so install a recent one, e.g. `brew install python@3.12`).

```bash
git clone https://github.com/redjohn-sudo/root-harness
cd root-harness
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

For Claude: install [Claude Code](https://claude.com/claude-code) and run
`claude` once to sign in with your plan. Other agents need their key (typed
once in the app) or a local Ollama.

**On your phone:** in the app, Settings, *Use from my phone*: open the address
it shows in Safari (type `http://` in full), sign in, then *Add to Home Screen*.
With your computer on, the phone drives its agents; computer off, the phone
still has your friends, your memory and vibe code.

**Vibe code:** Settings, *Vibe code*, *Create my workshop* (a private
`root-harness-runner` repository), then add two keys yourself, once:

```bash
claude setup-token
gh secret set CLAUDE_CODE_OAUTH_TOKEN -R <you>/root-harness-runner
gh auth token | gh secret set RH_GITHUB_TOKEN -R <you>/root-harness-runner
```

and turn on *GitHub on my phone* to vibe code from the phone.

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
Claude Code sessions stay on the computer that ran them. Vibe code is not live
(a GitHub machine starts in about a minute) and uses your GitHub Actions minutes
and your Claude plan.

## License

root-harness is free software under the [GNU AGPL v3](LICENSE). Use it, study
it, change it, share it. If you change it and offer it to others (even as an
online service), you share your changes under the same license: nobody can lock
it up. The name root-harness and Root's pixel head are the author's own work.

Copyright (C) 2026 Vincent Roumane
