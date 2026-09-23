#!/usr/bin/env python3
"""Add bounded routing context. Never block, mutate, or call another service."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys

LIMIT = 65536
LINEAR = re.compile(r"(?<![A-Za-z])linear(?![A-Za-z])", re.I)


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


def context(payload, skills_root):
    if not isinstance(payload, dict):
        return None
    event = payload.get("hook_event_name")
    if event not in ("UserPromptSubmit", "SessionStart"):
        return None
    if event == "SessionStart" and payload.get("source") not in ("resume", "compact"):
        return None
    entry = Path(skills_root).expanduser().resolve(strict=True) / "linear" / "SKILL.md"
    if not read_regular(entry).strip():
        return None
    selected = event == "UserPromptSubmit" and isinstance(payload.get("prompt"), str) and LINEAR.search(payload["prompt"])
    if not selected:
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not Path(cwd).is_absolute():
            return None
        folder = Path(cwd).resolve(strict=True)
        if not folder.is_dir():
            return None
        for parent in (folder, *folder.parents):
            agent_file = parent / "AGENTS.md"
            if agent_file.exists() or agent_file.is_symlink():
                if LINEAR.search(read_regular(agent_file)):
                    selected = True
                    break
    if not selected:
        return None
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": (
        "Linearに関係する依頼では、ユーザー・AGENTS・所有IssueのスキルOFFを優先し、"
        "このHookだけでONへ変更しない。適用する担当は明示された有効版を優先し、"
        f"指定がなければ入口 {entry} を読み、必要なRefresh/PMへ接続する。"
        "読取だけの依頼は回答で完了し、適用外の仕事では使わない。"
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
