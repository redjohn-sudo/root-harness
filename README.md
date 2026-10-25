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

- **The loop** lives in the Claude Agent SDK: Claude thinks, picks a tool, sees
  the result, and continues. We just expose our tools to it. (`bridge_claude.py`)
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

## Plug a different model

v1 is centered on your Claude subscription. An **API-key path** (any
OpenAI-compatible provider, or the Anthropic API) is in `models.py` and on the
roadmap, so people with API credits or a local model (Ollama) can use it too.

## Roadmap

- [ ] Guided first-run setup (make step 2 painless)
- [ ] API-key path (OpenAI-compatible, Anthropic) and local models (Ollama)
- [ ] Richer "share" (a reusable agent setup a friend opens in one click)
- [ ] App icon and a one-file install
- [ ] Docs and examples for École 42

## License

MIT. See [LICENSE](LICENSE).
