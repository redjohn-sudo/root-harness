<p align="center"><img src="ui-src/assets/root-head.svg" width="96" alt="Root"></p>

# root-harness

One simple place for all your AI agents, the same on your computer and on your
phone. Talk to them, let them work, vibe code on GitHub from anywhere, and share
what they did with your friends, sealed end to end.

Open source (MIT). No server of ours: your account, your memory and your
messages live on your devices, and travel sealed.

## What you can do

- **Work with your agents.** Claude (the real Claude Code, on your Pro/Max
  plan), Codex, DeepSeek, Kimi, GLM, Ollama... Every model, effort and slash
  command; permission cards before anything risky; images; Esc to stop.
- **Vibe code from your phone, computer off.** Have an idea outside? Pick any of
  your GitHub repositories (or a new one), describe it: Claude Code builds it on
  GitHub's machines with your plan and opens a pull request you review.
- **Friends and groups.** Add friends with their ID, make groups, talk,
  sealed end to end (relays see neither the text nor who talks to whom).
- **Share your agents' work.** Send a conversation to a friend or a group; they
  read it, or continue it with their own agent.
- **One account, every device.** A pseudo and a password. Sign in on another
  computer or your phone: your conversations, folders, friends, background and
  keys come with you, sealed.

## Start

```bash
git clone https://github.com/redjohn-sudo/root-harness
cd root-harness
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
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

Honest limits: free relays promise no storage and may rate-limit; they see
your IP and when you connect. A stolen identity key would open past messages.
Claude Code sessions stay on the computer that ran them. Vibe code is not live
(a GitHub machine starts in about a minute) and uses your GitHub Actions minutes
and your Claude plan.
