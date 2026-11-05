#!/usr/bin/env python3
"""Advisory routing context for the linear-workflow skill.

DISARMED. This handler returns nothing until someone sets DISARMED = False
below and reinstalls deliberately. See hooks/README.md for why.

History: an earlier version of this file fired whenever the word "linear"
appeared in a prompt, or whenever any ancestor AGENTS.md mentioned "linear".
That matched "linear algebra", "linear regression", and every unrelated repo
whose AGENTS.md happened to reference Linear, so the package was uninstalled
on 2026-10-14 for interfering with other work. The trigger below is rewritten
to be opt-in per repository, and it still ships switched off.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys

# Set to False only when you intend this handler to inject context again, and
# only after confirming the opt-in markers below are present where you want it.
DISARMED = True

LIMIT = 65536

# A repository opts in by writing this exact marker into its AGENTS.md or
# CLAUDE.md. Nothing else arms the handler: the bare word "linear" does not.
OPT_IN_MARKER = "linear-workflow"
OPT_IN_FILES = ("AGENTS.md", "CLAUDE.md")

# Only used to decide whether the current prompt is about Linear at all, and
# only inside a repository that already opted in above.
LINEAR_HINT = re.compile(r"linear\.app|(?<![0-9A-Za-z])[A-Z]{2,5}-[0-9]{1,6}(?![0-9A-Za-z])")


def read_regular(path):
    path = path.resolve(strict=True)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("not a regular file")
        data = stream.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError("too large")
    return data.decode("utf-8")


def opted_in(cwd):
    """True only when an ancestor of cwd carries the explicit opt-in marker."""
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        return False
    folder = Path(cwd).resolve(strict=True)
    if not folder.is_dir():
        return False
    for parent in (folder, *folder.parents):
        for name in OPT_IN_FILES:
            candidate = parent / name
            if candidate.exists() or candidate.is_symlink():
                try:
                    if OPT_IN_MARKER in read_regular(candidate):
                        return True
                except (OSError, ValueError, UnicodeDecodeError):
                    continue
    return False


def context(payload, skills_root):
    if DISARMED:
        return None
    if not isinstance(payload, dict):
        return None
    event = payload.get("hook_event_name")
    if event not in ("UserPromptSubmit", "SessionStart"):
        return None
    if event == "SessionStart" and payload.get("source") not in ("resume", "compact"):
        return None
    if not opted_in(payload.get("cwd")):
        return None
    # A missing or unreadable entry means there is nothing to point at. Stay
    # silent rather than raising: a broken install must not disturb a session.
    try:
        entry = Path(skills_root).expanduser().resolve(strict=True) / "linear-workflow" / "SKILL.md"
        if not read_regular(entry).strip():
            return None
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if event == "UserPromptSubmit":
        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or not LINEAR_HINT.search(prompt):
            return None
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": (
        f"このリポジトリはLinearで仕事を追跡している。入口は {entry}。"
        "読取だけの依頼は読んで答えて終える。ユーザーの指示が優先で、"
        "この案内だけでスキルを使う判断にしない。"
    )}}


def main():
    try:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--skills-root", required=True)
        parser.add_argument("--owner")
        args = parser.parse_args()
        data = sys.stdin.buffer.read(LIMIT + 1)
        if len(data) > LIMIT:
            return
        result = context(json.loads(data), args.skills_root)
        if result:
            print(json.dumps(result, ensure_ascii=False))
    except (Exception, SystemExit):
        pass


if __name__ == "__main__":
    main()
