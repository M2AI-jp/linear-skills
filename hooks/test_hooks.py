"""Checks that the advisory handler stays silent, and is narrow when armed."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import route  # noqa: E402


def workspace(marker=True, skill=True):
    """Build a throwaway repo plus skills root; return (cwd, skills_root)."""
    root = Path(tempfile.mkdtemp())
    repo = root / "repo"
    (repo / "nested").mkdir(parents=True)
    if marker:
        (repo / "AGENTS.md").write_text(
            "Linearで仕事を追跡している。入口は linear-workflow。\n", encoding="utf-8")
    else:
        (repo / "AGENTS.md").write_text("linear algebra notes\n", encoding="utf-8")
    skills = root / "skills"
    if skill:
        entry = skills / "linear-workflow"
        entry.mkdir(parents=True)
        (entry / "SKILL.md").write_text("---\nname: linear-workflow\n---\n", encoding="utf-8")
    else:
        skills.mkdir()
    return repo / "nested", skills


def prompt_payload(cwd, text):
    return {"hook_event_name": "UserPromptSubmit", "prompt": text, "cwd": str(cwd)}


class Disarmed(unittest.TestCase):
    def test_ships_switched_off(self):
        self.assertTrue(route.DISARMED, "route.py must ship disarmed")

    def test_returns_nothing_even_for_a_valid_request(self):
        cwd, skills = workspace()
        payload = prompt_payload(cwd, "https://linear.app/matsunai/issue/MAT-123 を進めて")
        self.assertIsNone(route.context(payload, skills))


@mock.patch.object(route, "DISARMED", False)
class Armed(unittest.TestCase):
    def test_requires_the_repository_to_opt_in(self):
        cwd, skills = workspace(marker=False)
        payload = prompt_payload(cwd, "MAT-123 を進めて")
        self.assertIsNone(route.context(payload, skills))

    def test_opt_in_marker_is_inherited_from_an_ancestor(self):
        cwd, skills = workspace()
        payload = prompt_payload(cwd, "MAT-123 を進めて")
        result = route.context(payload, skills)
        self.assertIn("additionalContext", result["hookSpecificOutput"])

    def test_the_word_linear_alone_does_not_fire(self):
        cwd, skills = workspace()
        for text in ("linear algebra の説明をして", "線形回帰 linear regression", "linearity"):
            with self.subTest(text=text):
                self.assertIsNone(route.context(prompt_payload(cwd, text), skills))

    def test_issue_key_or_url_fires(self):
        cwd, skills = workspace()
        for text in ("MAT-123 の続き", "https://linear.app/x/project/y を見て"):
            with self.subTest(text=text):
                self.assertIsNotNone(route.context(prompt_payload(cwd, text), skills))

    def test_session_start_only_on_resume_or_compact(self):
        cwd, skills = workspace()
        base = {"hook_event_name": "SessionStart", "cwd": str(cwd)}
        self.assertIsNone(route.context({**base, "source": "startup"}, skills))
        self.assertIsNotNone(route.context({**base, "source": "resume"}, skills))

    def test_unknown_event_and_broken_input_are_silent(self):
        cwd, skills = workspace()
        self.assertIsNone(route.context({"hook_event_name": "Stop", "cwd": str(cwd)}, skills))
        self.assertIsNone(route.context("not a dict", skills))

    def test_missing_skill_entry_is_silent(self):
        cwd, skills = workspace(skill=False)
        self.assertIsNone(route.context(prompt_payload(cwd, "MAT-123"), skills))

    def test_oversize_files_are_ignored_without_raising(self):
        cwd, skills = workspace()
        (cwd.parent / "AGENTS.md").write_text("x" * (route.LIMIT + 10), encoding="utf-8")
        self.assertIsNone(route.context(prompt_payload(cwd, "MAT-123"), skills))


class Installer(unittest.TestCase):
    def test_install_refuses_without_the_explicit_flag(self):
        config = Path(tempfile.mkdtemp())
        _, skills = workspace()
        done = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("install.py")),
             "--config-dir", str(config), "--skills-root", str(skills)],
            capture_output=True, text=True)
        self.assertEqual(done.returncode, 1)
        self.assertIn("--enable-interception", done.stderr)
        self.assertFalse((config / "hooks.json").exists())

    def test_remove_is_allowed_and_leaves_other_handlers(self):
        config = Path(tempfile.mkdtemp())
        other = {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "echo hi"}]}]}}
        (config / "hooks.json").write_text(json.dumps(other), encoding="utf-8")
        _, skills = workspace()
        done = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("install.py")),
             "--config-dir", str(config), "--skills-root", str(skills), "--remove"],
            capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads((config / "hooks.json").read_text()), other)


if __name__ == "__main__":
    unittest.main()
