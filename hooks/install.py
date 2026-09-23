#!/usr/bin/env python3
"""Install only this package's advisory handlers; never edit hook trust."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys
import tempfile

OWNER = "linear-harness-router-v1"
EVENTS = ("UserPromptSubmit", "SessionStart")


def safe_path(path):
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f"Symlink path is not supported: {part}")


def owned(handler, config):
    if handler.get("type") != "command":
        return False
    try:
        words = shlex.split(handler.get("command", ""))
        script = Path(words[1])
        return (len(words) == 6 and words[2] == "--skills-root" and
                words[4:] == ["--owner", OWNER] and script.name == "route.py" and
                re.fullmatch(r"[0-9a-f]{64}", script.parent.name) is not None and
                script.parent.parent == config / "linear-harness")
    except (ValueError, IndexError, TypeError):
        return False


def validate(data):
    if not isinstance(data, dict) or set(data) - {"hooks", "description"}:
        raise ValueError("Unknown hooks.json top-level structure; no configuration saved")
    if "description" in data and not isinstance(data["description"], str):
        raise ValueError("Invalid description")
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("hooks must be an object")
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            raise ValueError(f"Unknown event structure: {event}")
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise ValueError(f"Unknown handler group: {event}")
            if any(not isinstance(h, dict) or not isinstance(h.get("type"), str) for h in group["hooks"]):
                raise ValueError(f"Unknown handler: {event}")


def atomic_write(path, data):
    safe_path(path)
    fd, temporary = tempfile.mkstemp(prefix=".linear-harness-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install(config, skills, remove=False, source=None):
    config = Path(config).expanduser().resolve()
    skills = Path(skills).expanduser().resolve()
    safe_path(config)
    target = config / "hooks.json"
    safe_path(target)
    if target.exists() and not target.is_file():
        raise ValueError("hooks.json must be a regular file")
    old = target.read_bytes() if target.exists() else None
    if old is not None and len(old) > 1048576:
        raise ValueError("hooks.json exceeds 1 MiB")
    data = json.loads(old) if old is not None else {"hooks": {}}
    validate(data)
    updated = copy.deepcopy(data)
    hooks = updated.setdefault("hooks", {})
    for event in EVENTS:
        if event not in hooks:
            continue
        groups = []
        for original in hooks[event]:
            group = copy.deepcopy(original)
            group["hooks"] = [h for h in group["hooks"] if not owned(h, config)]
            if group["hooks"] or not original["hooks"]:
                groups.append(group)
        hooks[event] = groups
    script_bytes = None
    destination = None
    if not remove:
        entry = skills / "linear" / "SKILL.md"
        entry = entry.resolve(strict=True)
        if not entry.is_file() or not entry.read_bytes().strip():
            raise ValueError(f"Missing skill entry: {entry}")
        source = (Path(source) if source else Path(__file__).with_name("route.py")).resolve(strict=True)
        safe_path(source)
        script_bytes = source.read_bytes()
        digest = hashlib.sha256(script_bytes).hexdigest()
        destination = config / "linear-harness" / digest / "route.py"
        safe_path(destination)
        if destination.exists() and destination.read_bytes() != script_bytes:
            raise ValueError("Content-addressed route.py has unexpected content")
        command = shlex.join([sys.executable, str(destination), "--skills-root", str(skills), "--owner", OWNER])
        handler = {"type": "command", "command": command, "timeout": 3}
        hooks.setdefault("UserPromptSubmit", []).append({"hooks": [handler]})
        hooks.setdefault("SessionStart", []).append({"matcher": "^(resume|compact)$", "hooks": [copy.deepcopy(handler)]})
    if updated == data:
        if destination and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(destination, script_bytes)
            return "Restored missing route.py; configuration unchanged"
        return "Unchanged"
    serialized = (json.dumps(updated, ensure_ascii=False, indent=2) + "\n").encode()
    # Validate every destination before touching the live configuration.
    backup = config / ("hooks.json.backup-" + hashlib.sha256(old).hexdigest()) if old is not None else None
    if backup:
        safe_path(backup)
        if backup.exists() and backup.read_bytes() != old:
            raise ValueError("Backup path has unexpected content")
    config.mkdir(parents=True, exist_ok=True)
    if destination:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            atomic_write(destination, script_bytes)
    if backup and not backup.exists():
        atomic_write(backup, old)
    if (target.read_bytes() if target.exists() else None) != old:
        raise ValueError("hooks.json changed concurrently; no configuration saved")
    atomic_write(target, serialized)
    return "Removed owned handlers" if remove else "Installed; review and trust the definitions with Codex /hooks"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", default="~/.codex")
    parser.add_argument("--skills-root", default="~/.codex/skills")
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args()
    try:
        print(install(args.config_dir, args.skills_root, args.remove))
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f"Not installed: {exc}\n")


if __name__ == "__main__":
    main()
