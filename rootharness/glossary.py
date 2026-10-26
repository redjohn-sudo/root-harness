"""
The encyclopedia: the words that matter when you work with agents and models
(agents, LLM, RAG, code, security and CTF), one short clear definition each.

  - a base of terms ships with root-harness (glossary_base.json);
  - "learn as I work": after a turn, the agent you are using spots the
    technical words of that exchange you may not know, and adds them;
  - tapping a word opens a side question to that same agent, like /btw:
    it does not touch your main conversation.

Your encyclopedia lives in ~/.root-harness/glossary.json and travels with your
sealed memory to your other devices.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

HOME = Path(os.environ.get("ROOT_HARNESS_HOME") or Path.home() / ".root-harness")
FILE = HOME / "glossary.json"
BASE = Path(__file__).parent / "glossary_base.json"
CATEGORIES = ("agents", "llm", "rag", "code", "security")

on_change = lambda: None     # the window points this at the sync


def ident(term: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")


def _load() -> dict:
    try:
        d = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    d.setdefault("auto", False)
    d.setdefault("terms", {})          # id -> {term, def, cat, source, added}
    d.setdefault("hidden", [])         # base terms you removed
    return d


def _save(d: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(FILE)
    on_change()


def base() -> list[dict]:
    return json.loads(BASE.read_text(encoding="utf-8"))


def listing() -> dict:
    d = _load()
    items = {ident(b["term"]): {**b, "source": "base", "added": 0} for b in base()}
    items.update(d["terms"])
    for h in d["hidden"]:
        items.pop(h, None)
    terms = [{"id": k, **v} for k, v in items.items()]
    terms.sort(key=lambda t: t["term"].lower())
    return {"auto": d["auto"], "terms": terms}


def known() -> set[str]:
    return {t["term"].lower() for t in listing()["terms"]}


def add(term: str, definition: str, cat: str = "", source: str = "you") -> dict | None:
    term, definition = " ".join((term or "").split())[:60], " ".join((definition or "").split())[:420]
    if not term or not definition or term.lower() in known():
        return None
    d = _load()
    k = ident(term)
    entry = {"term": term, "def": definition, "cat": cat if cat in CATEGORIES else "code",
             "source": source[:40], "added": int(time.time())}
    d["terms"][k] = entry
    if k in d["hidden"]:
        d["hidden"].remove(k)
    _save(d)
    return {"id": k, **entry}


def remove(k: str) -> None:
    d = _load()
    d["terms"].pop(k, None)
    if any(ident(b["term"]) == k for b in base()) and k not in d["hidden"]:
        d["hidden"].append(k)
    _save(d)


def set_auto(on: bool) -> None:
    d = _load()
    d["auto"] = bool(on)
    _save(d)


def auto() -> bool:
    return _load()["auto"]


def merge(remote: dict) -> None:
    """Another device's encyclopedia joins this one (sync)."""
    d = _load()
    for k, v in (remote.get("terms") or {}).items():
        d["terms"].setdefault(k, v)
    d["hidden"] = sorted(set(d["hidden"]) | set(remote.get("hidden") or []))
    _save(d)


def raw() -> dict:
    return _load()


# -- what the agent is asked -------------------------------------------------------

EXTRACT = """From this exchange between a person and an AI agent, pick at most {n} technical
terms about code, AI, LLMs, agents, RAG or security that a beginner might not know
and that are NOT in this list: {known}.
Use the dictionary form of each term (memoization, not memoized; a function name stays as is).
For each, write one short definition (one or two sentences, under 45 words) that a
beginner understands right away, concrete, no jargon left unexplained.
Answer with JSON only: [{{"term": "...", "def": "...", "cat": "agents|llm|rag|code|security"}}].
If there is no such term, answer [].

The exchange:
{exchange}"""


def parse_terms(text: str) -> list[dict]:
    m = re.search(r"\[[\s\S]*\]", text or "")
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except ValueError:
        return []
    return [i for i in items if isinstance(i, dict) and i.get("term") and i.get("def")]
