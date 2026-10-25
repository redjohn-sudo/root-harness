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

## Encrypted channels with other users

Talk to other root-harness users in end-to-end encrypted channels (one-to-one
or small groups), over [Nostr](https://nostr.com) private messages (NIP-17,
NIP-44 encryption, NIP-59 gift wraps).

- Your identity is a key made on your machine and kept in the system keychain.
  No account, no email, no phone number. Give friends your ID (`npub1...`).
- Each message is sealed separately for each member. Public relays only carry
  sealed blobs: they see neither the text, nor the sender, nor the channel's
  name or members.
- Messages from people you have not added wait in **Requests**.
- Honest limits: relays see your IP address and when you connect; a stolen key
  would open past messages (no forward secrecy), hence the keychain.
- Your agent never reads or writes in a channel by itself.

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
