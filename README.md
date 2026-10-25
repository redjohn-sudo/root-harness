# root-harness

Talk to an AI agent in a small window, and actually **see what it does**.

root-harness runs your agent on **your own Claude Pro/Max subscription** (through
the official Claude Agent SDK), with no terminal to live in. Every step is shown
in plain words: what the agent reads, which tool it wants to run, and what came
back. It asks you before anything that changes your machine. Made for people
starting out with AI, including students at École 42.

> Status: **early (v0.1)**. The engine and window are here; onboarding, the
> API-key path and packaging are on the roadmap below. Issues and PRs welcome.

## Why

Agentic AI is powerful but it usually lives in a terminal, and you can't see
what it is doing. root-harness gives it a window, shows every move, and puts a
permission gate in front of anything risky, so a beginner can learn how an agent
actually works, and trust it.

## Quickstart

```bash
# 1. Get the code
git clone https://github.com/redjohn-sudo/root-harness.git
cd root-harness
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. One-time: sign in with your Claude subscription (uses Claude Code's login)
#    Install Node, then:
npm install -g @anthropic-ai/claude-code
claude            # follow the sign-in once, then quit

# 3. Run
python app.py
```

A window opens. Ask it something. When it wants to write a file or run a
command, you get an **Allow / Deny** card.

> Honest note: step 2 is the one terminal step, and it is exactly what we want
> to make painless. A guided first-run setup is the top item on the roadmap.

## How it works

Three small ideas, each in one readable file:

- **The brain** is yours to pick: Claude, Codex, or any API key. Same window,
  same tools, same permission cards. (`brains.py`)
- **The tools** are a short, safe list you can read in full: read a file, list a
  folder, write a file, run a command. (`tools.py`)
- **The permission gate** sits in front of anything that changes your machine.
  No gate, no action. (`permissions.py`)

The window (`window.py` + `ui/`) streams every step to the screen and routes
each permission question to an Allow / Deny card.

See [docs/how-it-works.md](docs/how-it-works.md) for the walkthrough.

## Add your own tool

```python
from rootharness.tools import register

@register("weather", "Get the weather for a city.", {"city": str})
def weather(city: str) -> str:
    ...
```

A read-only tool runs freely; a tool that changes something calls
`permissions.ask(...)` first. See [examples/add_your_own_tool.py](examples/add_your_own_tool.py).

## Everything your terminal does, in a window

With Claude, root-harness runs **the real Claude Code**: your settings, CLAUDE.md,
memory, skills, MCP servers, agents and every slash command (`/context`,
`/compact`, `/usage`, your own skills...). Nothing is re-implemented, only shown:

- every model your plan offers (`/model`), every effort up to `max`, and `ultracode`
- the permission modes, with **Shift+Tab** as in the terminal: ask, accept edits, plan, auto
- **Esc** stops the answer; the status bar shows the real context usage
- permission questions become Allow / Deny cards; when Claude asks you to choose, the options become buttons
- paste (Cmd+V) or drop images: they go with your next message, to any brain that can see
- every conversation is kept, **sorted by agent**, and you can make **folders** and drag
  conversations into them; your terminal sessions are listed too, and continue here in a copy

## Your account (local only)

The first launch asks for a pseudo (any one) and a password. There is no server
and no sign-up anywhere: the password locks your identity key on your machine
(NIP-49: scrypt + XChaCha20-Poly1305). In Settings, **Stay signed in** keeps the
unlocked key in the system keychain so root-harness opens without asking; off,
the password is asked at each launch. A forgotten password cannot be recovered:
you can start a new account, with a new ID.

Note: the password protects your identity, not your agent conversations, which
stay readable on disk by anyone using your computer account.

### The same account on every machine

On another machine, choose **I already have an account** and type your pseudo
and password: the whole memory of the account comes back (conversations and
folders, settings and background, brains, models and efforts, contacts and
channels, API keys). There is still no server of ours:

- your pseudo and password go through a slow function (scrypt, 256 MB) that
  gives a *login key*; your locked identity is published under it, sealed to
  it, so relays never see your pseudo, your password, or which ID it belongs to;
- the memory is cut into pieces sealed to yourself (NIP-44), stored as app
  data (NIP-78) under random-looking labels, on several relays, and republished
  when it changes; deletions travel too.

Honest limits: free relays promise no storage and may rate-limit or drop data;
they see that your ID stores sealed pieces and when. Claude Code sessions stay
on the machine that ran them; elsewhere Claude continues with the conversation
given as context.

## Encrypted channels with other users

Talk to other root-harness users in end-to-end encrypted channels (one-to-one
or small groups), over [Nostr](https://nostr.com) private messages (NIP-17,
NIP-44 encryption, NIP-59 gift wraps).

- Your identity is the key of your local account, locked by your password.
  No email, no phone number. Give friends your ID (`npub1...`); your pseudo
  travels inside the sealed messages, never in public.
- Each message is sealed separately for each member. Public relays only carry
  sealed blobs: they see neither the text, nor the sender, nor the channel's
  name or members.
- Messages from people you have not added wait in **Requests**.
- Honest limits: relays see your IP address and when you connect; a stolen key
  would open past messages (no forward secrecy), hence the keychain.
- Your agent never reads or writes in a channel by itself.

## Use root-harness from your phone

Your phone becomes a remote for the root-harness running on your computer:
turn on **Settings, Phone, Use from my phone**, open the address it shows in
Safari, sign in with your pseudo and password, then *Add to Home Screen*.
The agent keeps running on your computer (Claude Code cannot run on a phone);
the phone talks to it through sealed messages, so there is no port to open
and nothing readable on the relays. Permission cards show on the phone too.
Off by default, and per computer. See [mobile/](mobile/).

## Vibe code from your phone, computer off: Claude on GitHub

Claude Code can also work in one of your repositories on **GitHub's machines**,
with your Claude Pro/Max plan, so no computer has to stay on.

1. On the computer, **Settings, Claude on GitHub**: pick a repository and
   install the workflow (one commit). Then add your Claude token yourself:
   `claude setup-token`, then `gh secret set CLAUDE_CODE_OAUTH_TOKEN -R <repo>`.
2. On the phone, the **GitHub** tab: paste a fine-grained GitHub token for that
   repository (Issues read/write, Contents read, Actions read), pick the repo,
   and describe what to build.

Each conversation is an issue; Claude answers in a progress comment and gives
you the branch it worked on, with a link to open a pull request. Only the
repository owner can start it, so nobody else spends your plan. It is not live
like the computer (each request starts a machine, about a minute), and you
review the branch before anything is merged.

## Commands

Type `/` in the message box. Arrows to move, Enter or Tab to pick. With Claude,
the list also holds all of your Claude Code commands.

| Command | What it does |
|---|---|
| `/model` | change the model (Sonnet, Opus, GPT, Kimi...), the conversation goes on |
| `/effort` | how hard it thinks (low to max, when the model supports it) |
| `/brain` | change the brain, starts a new conversation |
| `/clear` | new conversation, same brain |
| `/tools` | what your agent can do, and what asks you first |
| `/status` | brain, model and effort right now |
| `/background` | change the background |
| `/export` | save the conversation as a page |
| `/mode` | ask, accept edits, plan or auto (or Shift+Tab) |
| `/help` | all commands |

## Pick your brain

Click the brain icon on the left (or type `/brain`) and choose who thinks for
your agent. One brain per provider; pick its model with `/model`:

| Brain | What you need | How it runs |
|---|---|---|
| Claude (every model your plan offers) | a Claude Pro/Max plan | the real Claude Code, through the Agent SDK (`bridge_claude.py`) |
| Codex (every model Codex lists) | a ChatGPT plan or OpenAI key | Codex app server (`bridge_codex.py`) |
| DeepSeek, Kimi, GLM, Claude API | an API key | our own short loop (`bridge_api.py`) |
| Ollama | nothing, it runs on your machine | our own short loop (`bridge_api.py`) |

Keys are typed once in the window and kept in `~/.root-harness/.env`, readable
by you only. Any other OpenAI-compatible provider can be added in
`~/.root-harness/brains.json`.

## Roadmap

- [ ] Guided first-run setup (make step 2 painless)
- [x] Pick your brain: Claude, Codex, API keys, local models (Ollama)
- [ ] Richer "share" (a reusable agent setup a friend opens in one click)
- [ ] App icon and a one-file install
- [ ] Docs and examples for École 42

## License

MIT. See [LICENSE](LICENSE).
