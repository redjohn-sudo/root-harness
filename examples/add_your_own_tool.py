"""
Add your own tool in a few lines.

Run this file to register a tool, then launch the app: `python app.py`.
A read-only tool runs freely. A tool that changes something must call
permissions.ask(...) first, which shows an Allow / Deny card in the window.
"""
from rootharness.tools import register
from rootharness import permissions


# A read-only tool: safe, runs without asking.
@register("reverse", "Reverse a piece of text.", {"text": str},
          kind=permissions.READ_ONLY)
def reverse(text: str) -> str:
    return text[::-1]


# A tool that changes something: ask first.
@register("make_note", "Append a line to notes.txt in the current folder.",
          {"line": str})
def make_note(line: str) -> str:
    if not permissions.ask("Append to notes.txt", {"line": line}):
        return "Denied by the user."
    with open("notes.txt", "a", encoding="utf-8") as f:
        f.write(line + "\n")
    return "Added the note."


if __name__ == "__main__":
    print("Registered:", "reverse", "make_note")
    print("Now run:  python app.py")
