"""
Vibe code: Claude Code builds your ideas in any of your GitHub repositories,
on GitHub's machines, with your Claude plan. Your computer can stay off.

One private repository, <you>/root-harness-runner, is the workshop: each idea
is an issue there ("repo: owner/name" or "new: name" on its first line), your
comments continue it, and the workflow (github/root-harness-runner.yml) runs
Claude Code in the target repository, on a branch, ending with a pull request.

The computer talks to GitHub with the `gh` command; the phone with a GitHub
token from your account's sealed memory (see host-phone.js). Same issues,
same comments: both see the same thing.
"""
from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

RUNNER = "root-harness-runner"
WORKFLOW = ".github/workflows/root-harness-vibe.yml"
TEMPLATE = Path(__file__).parent / "github" / "root-harness-runner.yml"
LABEL = "root-harness-vibe"
SECRETS = ("CLAUDE_CODE_OAUTH_TOKEN", "RH_GITHUB_TOKEN")


def _gh(*args, input_text: str | None = None, timeout: int = 40) -> str:
    out = subprocess.run(["gh", *args], capture_output=True, text=True, input=input_text, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or out.stdout).strip()[:300])
    return out.stdout


def login() -> str:
    return json.loads(_gh("api", "user"))["login"]


def runner() -> str:
    return f"{login()}/{RUNNER}"


def status() -> dict:
    """Is the workshop ready? What is missing, in plain words."""
    try:
        r = runner()
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return {"ready": False, "why": "Sign in to GitHub on this computer first: gh auth login", "step": "gh"}
    try:
        _gh("api", f"repos/{r}")
    except RuntimeError:
        return {"ready": False, "why": "Your vibe-code workshop is not created yet.", "step": "create", "runner": r}
    try:
        _gh("api", f"repos/{r}/contents/{WORKFLOW}")
    except RuntimeError:
        return {"ready": False, "why": "The workshop needs its workflow.", "step": "create", "runner": r}
    try:
        names = {s["name"] for s in json.loads(_gh("api", f"repos/{r}/actions/secrets"))["secrets"]}
    except (RuntimeError, ValueError, KeyError):
        names = set()
    missing = [s for s in SECRETS if s not in names]
    if missing:
        return {"ready": False, "why": "Two keys to add, by you, once.", "step": "secrets", "runner": r, "missing": missing,
                "commands": {"CLAUDE_CODE_OAUTH_TOKEN": f"claude setup-token\ngh secret set CLAUDE_CODE_OAUTH_TOKEN -R {r}",
                             "RH_GITHUB_TOKEN": f"gh auth token | gh secret set RH_GITHUB_TOKEN -R {r}"}}
    return {"ready": True, "runner": r}


def create() -> dict:
    """Make the private workshop repository and put the workflow in it."""
    r = runner()
    try:
        _gh("api", f"repos/{r}")
    except RuntimeError:
        _gh("repo", "create", r, "--private", "--add-readme", "--description",
            "root-harness: Claude builds my ideas here, in any of my repositories")
    body = {"message": "root-harness: vibe-code workflow", "content": base64.b64encode(TEMPLATE.read_bytes()).decode()}
    try:
        body["sha"] = json.loads(_gh("api", f"repos/{r}/contents/{WORKFLOW}"))["sha"]
    except RuntimeError:
        pass
    _gh("api", "-X", "PUT", f"repos/{r}/contents/{WORKFLOW}", "--input", "-", input_text=json.dumps(body))
    try:
        _gh("label", "create", LABEL, "-R", r, "--color", "3f9d84", "--description", "An idea for Claude, from root-harness")
    except RuntimeError:
        pass
    return status()


def repos() -> list[str]:
    data = json.loads(_gh("repo", "list", "--limit", "300", "--json", "nameWithOwner,viewerPermission"))
    return [d["nameWithOwner"] for d in data if d.get("viewerPermission") in ("ADMIN", "MAINTAIN", "WRITE")
            and not d["nameWithOwner"].endswith("/" + RUNNER)]


def projects() -> list[dict]:
    issues = json.loads(_gh("api", f"repos/{runner()}/issues?labels={LABEL}&state=all&sort=updated&per_page=50"))
    out = []
    for i in issues:
        first = (i.get("body") or "").split("\n", 1)[0]
        repo = first.split(":", 1)[1].strip() if ":" in first else "?"
        out.append({"number": i["number"], "title": i["title"], "repo": repo, "state": i["state"],
                    "updated": _ms(i["updated_at"])})
    return out


def _ms(iso: str) -> int:
    from datetime import datetime
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def _clean(text: str) -> str:
    return (text or "").split("<!-- rh:")[0].strip()


def thread(number: int) -> dict:
    r = runner()
    issue = json.loads(_gh("api", f"repos/{r}/issues/{number}"))
    comments = json.loads(_gh("api", f"repos/{r}/issues/{number}/comments?per_page=100"))
    me = issue["user"]["login"]
    first, _, idea = (issue.get("body") or "").partition("\n")
    msgs = [{"id": f"i{number}", "bot": False, "text": idea.strip(), "updated": issue["updated_at"]}]
    working = False
    for c in comments:
        bot = c["user"]["login"] != me
        msgs.append({"id": str(c["id"]), "bot": bot, "text": _clean(c["body"]), "updated": c["updated_at"]})
        if bot:
            working = "<!-- rh:working -->" in (c["body"] or "")
    if comments and comments[-1]["user"]["login"] == me:
        working = True                     # sent, the machine is starting
    return {"repo": first.split(":", 1)[-1].strip(), "messages": msgs, "working": working}


def send(repo: str, text: str, number: int = 0) -> dict:
    r = runner()
    if not number:
        first = f"new: {repo[4:]}" if repo.startswith("new:") else f"repo: {repo}"
        title = " ".join(text.split())[:70]
        issue = json.loads(_gh("api", "-X", "POST", f"repos/{r}/issues", "--input", "-",
                               input_text=json.dumps({"title": title, "body": f"{first}\n\n{text}", "labels": [LABEL]})))
        return {"number": issue["number"]}
    _gh("api", "-X", "POST", f"repos/{r}/issues/{number}/comments", "--input", "-", input_text=json.dumps({"body": text}))
    return {"number": number}
