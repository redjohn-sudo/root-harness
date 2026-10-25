# How it works

root-harness is small on purpose. You can read the whole engine in a few
minutes. Here is the walkthrough.

## 1. The loop

You do not write the loop yourself. Claude, driven by the **Claude Agent SDK**,
runs it: it reads your message, decides whether it needs a tool, uses it, reads
the result, and continues until it has an answer.

What we provide is the **list of tools** Claude is allowed to use. Its own
built-in tools are turned off, so it can only do what you gave it. That code is
`rootharness/bridge_claude.py`.

## 2. The tools

A tool is just a Python function with a name, a short description and a schema.
The starter set in `rootharness/tools.py` is deliberately short:

- `read_file`, `list_dir` : read-only, run freely.
- `write_file`, `run_command` : change your machine, so they ask first.

Adding one is three lines (see `examples/add_your_own_tool.py`).

## 3. The permission gate

This is the idea we care about most. Any tool that changes something calls
`permissions.ask(...)`, which shows an **Allow / Deny** card in the window and
waits for you. No click, no action. The default is to deny, so a bug never runs
a risky tool silently. That code is `rootharness/permissions.py`.

## 4. The window

`rootharness/window.py` opens a native window (pywebview) that loads `ui/`.
JavaScript calls into Python with `window.pywebview.api.*`; Python pushes each
step back by calling `onEvent(...)` in the page. That is why you see the agent's
text, its tool calls and its results as they happen, instead of a terminal log.

## The flow, in one picture

```
you type  ->  Claude thinks  ->  wants a tool
                                    |
                      read-only? ---+--- changes things?
                        run it           ask you (Allow / Deny)
                                    |
                      result shown in the window
                                    |
                      Claude continues, or answers
```
