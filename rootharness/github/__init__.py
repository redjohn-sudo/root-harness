"""
Claude on GitHub: Claude Code working in one of your repositories on GitHub's
machines, with your Claude Pro/Max plan, so no computer has to stay on.
Vibe coding from your phone included.

How it works: each conversation is an issue labelled "root-harness". Your
messages are comments starting with "@claude"; the workflow in
root-harness-claude.yml starts Claude Code, which answers in a progress comment
it keeps up to date, and gives the branch it worked on, with a link to open a
pull request. You review before anything is merged.

Setting up a repository (from the computer, with the `gh` command):
  1. install the workflow file (a commit on the default branch);
  2. add the secret CLAUDE_CODE_OAUTH_TOKEN yourself: `claude setup-token`,
     then `gh secret set CLAUDE_CODE_OAUTH_TOKEN -R <owner/repo>`.
     root-harness never sees that token.
"""
from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

WORKFLOW = ".github/workflows/root-harness-claude.yml"
TEMPLATE = Path(__file__).parent / "root-harness-claude.yml"
LABEL = "root-harness"


def _gh(*args, input_text: str | None = None, timeout: int = 30):
    out = subprocess.run(["gh", *args], capture_output=True, text=True, input=input_text, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or out.stdout).strip()[:300])
    return out.stdout


def available() -> bool:
    try:
        _gh("auth", "status")
        return True
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return False


def repos() -> list[dict]:
    """Your repositories where you can push."""
    data = json.loads(_gh("repo", "list", "--limit", "200", "--json",
                          "nameWithOwner,isPrivate,viewerPermission,updatedAt"))
    return [{"repo": r["nameWithOwner"], "private": r["isPrivate"]} for r in data
            if r.get("viewerPermission") in ("ADMIN", "MAINTAIN", "WRITE")]


def status(repo: str) -> dict:
    """Is this repository ready: workflow installed, secret added?"""
    try:
        _gh("api", f"repos/{repo}/contents/{WORKFLOW}")
        workflow = True
    except RuntimeError:
        workflow = False
    try:
        names = [s["name"] for s in json.loads(_gh("api", f"repos/{repo}/actions/secrets"))["secrets"]]
        secret = "CLAUDE_CODE_OAUTH_TOKEN" in names
    except (RuntimeError, ValueError, KeyError):
        secret = False
    return {"repo": repo, "workflow": workflow, "secret": secret, "ready": workflow and secret,
            "secret_command": f"claude setup-token\ngh secret set CLAUDE_CODE_OAUTH_TOKEN -R {repo}"}


def install(repo: str) -> dict:
    """Add the workflow file to the repository (one commit), and the label."""
    body = {"message": "Add root-harness: Claude Code on GitHub",
            "content": base64.b64encode(TEMPLATE.read_bytes()).decode()}
    try:
        current = json.loads(_gh("api", f"repos/{repo}/contents/{WORKFLOW}"))
        body["sha"] = current["sha"]              # update it if it is already there
    except RuntimeError:
        pass
    _gh("api", "-X", "PUT", f"repos/{repo}/contents/{WORKFLOW}", "--input", "-", input_text=json.dumps(body))
    try:
        _gh("label", "create", LABEL, "-R", repo, "--color", "3f9d84",
            "--description", "Conversations with Claude from root-harness")
    except RuntimeError:
        pass                                      # already there
    return status(repo)
