#!/usr/bin/env python3
"""Advisory routing context for the linear-workflow skill.

DISARMED. This handler returns nothing until someone sets DISARMED = False
below and reinstalls deliberately. See hooks/README.md for why.

History: the first version fired whenever the word "linear" appeared in a
prompt, or whenever any ancestor AGENTS.md mentioned "linear". That matched
"linear algebra" and every unrelated repository whose AGENTS.md happened to
reference Linear, so the package was uninstalled on 2026-10-14 for
interfering with other work.

The rewrite that followed kept the same shape of defect in three places,
found by an independent review of the tests: the opt-in marker was matched
as a substring, so a document merely explaining how to opt in switched the
handler on; the search for it walked every ancestor to the filesystem root,
so one marker in a home directory opted in every repository below it; and
the prompt gate accepted any uppercase-dash-digits token, so UTF-8, GPT-4
and ISO-8601 all matched. All three are fixed here: the marker must be a
whole line, the search stops at the repository root, and issue ids only
count for team keys the repository names itself.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys

# Set to False only when you intend this handler to inject context again, and
# only after confirming the opt-in line is present where you want it.
DISARMED = True

LIMIT = 65536

# A repository opts in with a line of its own in AGENTS.md or CLAUDE.md:
#
#     linear-workflow: on
#     linear-workflow: on (MAT)
#     linear-workflow: on (MAT, ENG)
#
# The whole line must match, so prose and backticked examples that mention
# the marker do not switch anything on. Team keys in parentheses are the
# issue-id prefixes this repository wants recognised in a prompt; with none
# given, only a linear.app URL counts.
OPT_IN_FILES = ("AGENTS.md", "CLAUDE.md")
OPT_IN_LINE = re.compile(
    r"^[ \t]*linear-workflow:[ \t]*on[ \t]*"
    r"(?:\([ \t]*([A-Z][A-Z0-9]{1,7}(?:[ \t]*,[ \t]*[A-Z][A-Z0-9]{1,7})*)[ \t]*\))?[ \t]*$"
)

# Marks a repository root, so the walk upward has somewhere to stop. A file
# rather than a directory means a linked worktree.
REPO_MARKER = ".git"

LINEAR_URL = re.compile(r"(?<![0-9A-Za-z])linear\.app(?![0-9A-Za-z])", re.I)

# SessionStart sources worth a reminder: the session lost its earlier
# context. install.py builds its matcher from this, and a test holds the two
# to the same value.
SESSION_START_SOURCES = ("resume", "compact")


def read_regular(path, follow_symlinks=False):
    """Read a small regular file. Refuses a symlinked final component.

    The parent is resolved but the leaf is opened with O_NOFOLLOW, so a
    symlinked AGENTS.md cannot pull in a file from outside the repository.
    Resolving the whole path first would defeat the flag.
    """
    path = Path(path)
    target = path.parent.resolve(strict=True) / path.name
    flags = os.O_RDONLY | os.O_NONBLOCK
    if not follow_symlinks:
        flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("not a regular file")
        data = stream.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError("too large")
    return data.decode("utf-8")


def search_roots(cwd):
    """Directories to look in: cwd up to and including its repository root.

    Without a repository root, only cwd itself, so a marker further up
    cannot reach down into unrelated directories.
    """
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        return []
    try:
        folder = Path(cwd).resolve(strict=True)
    except OSError:
        return []
    if not folder.is_dir():
        return []
    roots = []
    for parent in (folder, *folder.parents):
        roots.append(parent)
        marker = parent / REPO_MARKER
        if marker.is_dir() or marker.is_file():
            return roots
    return [folder]


def opted_in(cwd):
    """Return (opted_in, team_keys) for the repository containing cwd."""
    keys = set()
    found = False
    for parent in search_roots(cwd):
        for name in OPT_IN_FILES:
            candidate = parent / name
            if not (candidate.exists() or candidate.is_symlink()):
                continue
            try:
                text = read_regular(candidate)
            except (OSError, ValueError, UnicodeDecodeError):
                # One unreadable or oversized entry file must not decide for
                # the rest: keep looking.
                continue
            for line in text.splitlines():
                matched = OPT_IN_LINE.match(line)
                if matched:
                    found = True
                    if matched.group(1):
                        keys.update(k.strip() for k in matched.group(1).split(","))
    return found, sorted(keys)


def prompt_concerns_linear(prompt, team_keys):
    if not isinstance(prompt, str):
        return False
    if LINEAR_URL.search(prompt):
        return True
    for key in team_keys:
        if re.search(rf"(?<![0-9A-Za-z]){re.escape(key)}-[0-9]{{1,6}}(?![0-9A-Za-z])", prompt):
            return True
    return False


def context(payload, skills_root):
    if DISARMED:
        return None
    if not isinstance(payload, dict):
        return None
    event = payload.get("hook_event_name")
    if event not in ("UserPromptSubmit", "SessionStart"):
        return None
    if event == "SessionStart" and payload.get("source") not in SESSION_START_SOURCES:
        return None
    enabled, team_keys = opted_in(payload.get("cwd"))
    if not enabled:
        return None
    # A missing or unreadable entry means there is nothing to point at. Stay
    # silent rather than raising: a broken install must not disturb a session.
    try:
        entry = Path(skills_root).expanduser().resolve(strict=True) / "linear-workflow" / "SKILL.md"
        if not read_regular(entry, follow_symlinks=True).strip():
            return None
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if event == "UserPromptSubmit" and not prompt_concerns_linear(payload.get("prompt"), team_keys):
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
