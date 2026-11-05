"""Checks that the advisory handler stays silent, and is narrow when armed.

Hermetic: every fixture gets a `.git` marker so the search for the opt-in
line stops inside the fixture, and never reads an AGENTS.md belonging to the
machine running the tests. Temporary directories are cleaned up.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOOKS = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS))

import route  # noqa: E402

INSTALL = HOOKS / "install.py"
MARKER = "linear-workflow" + ": on"


class Fixture(unittest.TestCase):
    """Builds throwaway repositories and skills roots."""

    def temp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name)

    def repo(self, entry=MARKER, name="AGENTS.md", nested=True):
        """A repository with a .git marker and an optional entry file."""
        root = self.temp() / "repo"
        (root / "nested").mkdir(parents=True)
        (root / ".git").mkdir()
        if entry is not None:
            (root / name).write_text(f"# repo\n\n{entry}\n", encoding="utf-8")
        return (root / "nested") if nested else root, root

    def skills(self, body="---\nname: linear-workflow\n---\n"):
        root = self.temp() / "skills"
        entry = root / "linear-workflow"
        entry.mkdir(parents=True)
        if body is not None:
            (entry / "SKILL.md").write_text(body, encoding="utf-8")
        return root

    def prompt(self, cwd, text):
        return {"hook_event_name": "UserPromptSubmit", "prompt": text, "cwd": str(cwd)}


class Disarmed(Fixture):
    def test_ships_switched_off(self):
        self.assertTrue(route.DISARMED, "route.py must ship disarmed")

    def test_returns_nothing_even_for_a_valid_request(self):
        cwd, _ = self.repo()
        payload = self.prompt(cwd, "https://linear.app/x/issue/MAT-123 を進めて")
        self.assertIsNone(route.context(payload, self.skills()))


@mock.patch.object(route, "DISARMED", False)
class OptIn(Fixture):
    def test_requires_an_opt_in_line(self):
        cwd, _ = self.repo(entry=None)
        self.assertIsNone(route.context(self.prompt(cwd, "linear.app を見て"), self.skills()))

    def test_marker_must_be_a_whole_line_not_a_substring(self):
        """Prose about the marker, and backticked examples, must not opt in."""
        for text in (
            f"{MARKER}sen の予約を取る",
            f"絶対に {MARKER} にしないこと",
            f"opt in するには `{MARKER}` と書く",
            f"- {MARKER}",
            f"> {MARKER}",
        ):
            with self.subTest(text=text):
                cwd, _ = self.repo(entry=text)
                self.assertIsNone(
                    route.context(self.prompt(cwd, "linear.app"), self.skills()))

    def test_bare_marker_line_opts_in(self):
        cwd, _ = self.repo()
        self.assertIsNotNone(route.context(self.prompt(cwd, "linear.app"), self.skills()))

    def test_claude_md_is_also_read(self):
        cwd, _ = self.repo(name="CLAUDE.md")
        self.assertIsNotNone(route.context(self.prompt(cwd, "linear.app"), self.skills()))

    def test_marker_is_inherited_up_to_the_repository_root(self):
        cwd, root = self.repo()
        deeper = root / "nested" / "a" / "b"
        deeper.mkdir(parents=True)
        self.assertIsNotNone(route.context(self.prompt(deeper, "linear.app"), self.skills()))

    def test_the_walk_stops_at_the_repository_root(self):
        """A marker above the repository must not reach into it."""
        cwd, root = self.repo(entry=None)
        (root.parent / "AGENTS.md").write_text(f"{MARKER}\n", encoding="utf-8")
        self.assertIsNone(route.context(self.prompt(cwd, "linear.app"), self.skills()))

    def test_without_a_repository_root_only_the_working_directory_counts(self):
        base = self.temp()
        (base / "AGENTS.md").write_text(f"{MARKER}\n", encoding="utf-8")
        child = base / "child"
        child.mkdir()
        self.assertIsNone(route.context(self.prompt(child, "linear.app"), self.skills()))
        self.assertIsNotNone(route.context(self.prompt(base, "linear.app"), self.skills()))

    def test_a_symlinked_entry_file_is_refused(self):
        cwd, root = self.repo(entry=None)
        outside = self.temp() / "elsewhere.md"
        outside.write_text(f"{MARKER}\n", encoding="utf-8")
        os.symlink(outside, root / "AGENTS.md")
        self.assertIsNone(route.context(self.prompt(cwd, "linear.app"), self.skills()))

    def test_one_unreadable_entry_file_does_not_veto_the_others(self):
        cwd, root = self.repo(entry=None)
        (root / "AGENTS.md").write_text("x" * (route.LIMIT + 10), encoding="utf-8")
        (root / "CLAUDE.md").write_text(f"{MARKER}\n", encoding="utf-8")
        self.assertIsNotNone(route.context(self.prompt(cwd, "linear.app"), self.skills()))

    def test_a_nonexistent_working_directory_is_silent(self):
        missing = self.temp() / "gone"
        self.assertIsNone(route.context(self.prompt(missing, "linear.app"), self.skills()))
        self.assertEqual(route.opted_in(str(missing)), (False, []))

    def test_relative_and_missing_cwd_are_silent(self):
        for cwd in ("relative/path", None, 7):
            with self.subTest(cwd=cwd):
                self.assertEqual(route.search_roots(cwd), [])


@mock.patch.object(route, "DISARMED", False)
class Trigger(Fixture):
    def test_the_word_linear_alone_does_not_fire(self):
        cwd, _ = self.repo()
        for text in ("linear algebra の説明", "線形回帰 linear regression", "nonlinear.application"):
            with self.subTest(text=text):
                self.assertIsNone(route.context(self.prompt(cwd, text), self.skills()))

    def test_a_linear_url_fires_in_any_case(self):
        cwd, _ = self.repo()
        for text in ("https://linear.app/x/y", "Linear.app を開いて", "LINEAR.APP"):
            with self.subTest(text=text):
                self.assertIsNotNone(route.context(self.prompt(cwd, text), self.skills()))

    def test_unrelated_dashed_tokens_do_not_fire(self):
        """An issue id only counts for a team key the repository declared."""
        cwd, _ = self.repo()
        for text in ("UTF-8 に変換", "COVID-19 の統計", "GPT-4 を使う", "ISO-8601 形式",
                     "SHA-256 を計算", "RFC-2119 の MUST", "JIRA-4512 を見て", "MAT-123 の続き"):
            with self.subTest(text=text):
                self.assertIsNone(route.context(self.prompt(cwd, text), self.skills()))

    def test_declared_team_keys_fire(self):
        cwd, _ = self.repo(entry=f"{MARKER} (MAT, ENG)")
        for text in ("MAT-123 の続き", "ENG-7 を見て", "(MAT-900)"):
            with self.subTest(text=text):
                self.assertIsNotNone(route.context(self.prompt(cwd, text), self.skills()))
        for text in ("UTF-8 に変換", "MATCH-1 を見て", "XMAT-123"):
            with self.subTest(text=text):
                self.assertIsNone(route.context(self.prompt(cwd, text), self.skills()))

    def test_a_non_string_prompt_is_silent(self):
        cwd, _ = self.repo()
        self.assertIsNone(route.context(
            {"hook_event_name": "UserPromptSubmit", "prompt": {"text": "linear.app"},
             "cwd": str(cwd)}, self.skills()))

    def test_session_start_fires_only_on_resume_or_compact(self):
        cwd, _ = self.repo()
        base = {"hook_event_name": "SessionStart", "cwd": str(cwd)}
        skills = self.skills()
        self.assertEqual(route.SESSION_START_SOURCES, ("resume", "compact"))
        for source in route.SESSION_START_SOURCES:
            with self.subTest(source=source):
                self.assertIsNotNone(route.context({**base, "source": source}, skills))
        for source in ("startup", "clear", None):
            with self.subTest(source=source):
                self.assertIsNone(route.context({**base, "source": source}, skills))

    def test_unknown_event_and_broken_payloads_are_silent(self):
        cwd, _ = self.repo()
        skills = self.skills()
        for payload in ({"hook_event_name": "Stop", "cwd": str(cwd)},
                        {"hook_event_name": "PreToolUse", "cwd": str(cwd)},
                        {"cwd": str(cwd)}, "not a dict", None, []):
            with self.subTest(payload=payload):
                self.assertIsNone(route.context(payload, skills))

    def test_a_missing_or_empty_skill_entry_is_silent(self):
        cwd, _ = self.repo()
        for body in (None, "", "   \n"):
            with self.subTest(body=body):
                self.assertIsNone(route.context(self.prompt(cwd, "linear.app"), self.skills(body)))

    def test_the_advisory_names_the_entry_and_stays_advisory(self):
        cwd, _ = self.repo()
        skills = self.skills()
        out = route.context(self.prompt(cwd, "linear.app"), skills)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "UserPromptSubmit")
        self.assertIn(str((skills / "linear-workflow" / "SKILL.md").resolve()),
                      out["additionalContext"])
        self.assertIn("読取だけの依頼", out["additionalContext"])
        self.assertIn("ユーザーの指示が優先", out["additionalContext"])

    def test_session_start_reports_its_own_event_name(self):
        cwd, _ = self.repo()
        out = route.context({"hook_event_name": "SessionStart", "source": "resume",
                             "cwd": str(cwd)}, self.skills())
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")


class Process(Fixture):
    """What Codex actually runs: never blocks, never raises, always exit 0."""

    def run_hook(self, payload, skills, *, raw=None, args=None):
        argv = [sys.executable, str(HOOKS / "route.py")]
        argv += ["--skills-root", str(skills)] if args is None else args
        data = raw if raw is not None else json.dumps(payload)
        return subprocess.run(argv, input=data, capture_output=True, text=True)

    def test_disarmed_process_emits_nothing_and_exits_zero(self):
        cwd, _ = self.repo()
        done = self.run_hook(self.prompt(cwd, "linear.app"), self.skills())
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout.strip(), "")

    def test_malformed_input_exits_zero_without_output(self):
        skills = self.skills()
        for raw in ("", "   ", "not json", "[]", "null", '{"hook_event_name":', "x" * 70000):
            with self.subTest(raw=raw[:20]):
                done = self.run_hook(None, skills, raw=raw)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(done.stdout.strip(), "")

    def test_oversized_but_valid_input_is_bounded(self):
        """main() caps what it reads, so a huge valid payload still does nothing."""
        cwd, _ = self.repo()
        payload = self.prompt(cwd, "linear.app " + "あ" * 40000)
        self.assertGreater(len(json.dumps(payload)), route.LIMIT)
        done = self.run_hook(payload, self.skills())
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "")

    def test_missing_arguments_exit_zero_without_output(self):
        done = self.run_hook(None, None, raw="{}", args=[])
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout.strip(), "")

    def test_armed_process_prints_only_additional_context(self):
        """The one shape Codex may act on. Must never carry a decision."""
        cwd, _ = self.repo()
        skills = self.skills()
        source = (HOOKS / "route.py").read_text().replace("DISARMED = True", "DISARMED = False")
        armed = self.temp() / "route.py"
        armed.write_text(source, encoding="utf-8")
        done = subprocess.run(
            [sys.executable, str(armed), "--skills-root", str(skills)],
            input=json.dumps(self.prompt(cwd, "linear.app")), capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        payload = json.loads(done.stdout)
        self.assertEqual(list(payload), ["hookSpecificOutput"])
        self.assertEqual(sorted(payload["hookSpecificOutput"]),
                         ["additionalContext", "hookEventName"])
        for forbidden in ("decision", "block", "continue", "stopReason",
                          "permissionDecision", "hookEventName:"):
            self.assertNotIn(f'"{forbidden}"', done.stdout)


class Installer(Fixture):
    def config(self, existing=None):
        root = self.temp() / "codex"
        root.mkdir()
        if existing is not None:
            (root / "hooks.json").write_text(json.dumps(existing, indent=2) + "\n",
                                             encoding="utf-8")
        return root

    def install(self, config, skills, *extra):
        return subprocess.run(
            [sys.executable, str(INSTALL), "--config-dir", str(config),
             "--skills-root", str(skills), *extra],
            capture_output=True, text=True)

    def test_install_refuses_without_the_explicit_flag(self):
        config, skills = self.config(), self.skills()
        done = self.install(config, skills)
        self.assertEqual(done.returncode, 1)
        self.assertIn("--enable-interception", done.stderr)
        self.assertFalse((config / "hooks.json").exists())

    def test_install_refuses_without_a_usable_skill_entry(self):
        for body in (None, "", "   \n"):
            with self.subTest(body=body):
                config = self.config()
                done = self.install(config, self.skills(body), "--enable-interception")
                self.assertEqual(done.returncode, 1, done.stdout)
                self.assertFalse((config / "hooks.json").exists())

    def test_install_then_remove_restores_foreign_handlers_exactly(self):
        foreign = {"hooks": {
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "echo mine"}]}],
            "SessionStart": [{"matcher": "^startup$",
                              "hooks": [{"type": "command", "command": "echo start"}]}],
            "PreToolUse": [{"hooks": [{"type": "command", "command": "echo pre"}]}],
        }}
        config, skills = self.config(foreign), self.skills()
        before = (config / "hooks.json").read_bytes()

        done = self.install(config, skills, "--enable-interception")
        self.assertEqual(done.returncode, 0, done.stderr)
        after = json.loads((config / "hooks.json").read_text())

        # Foreign handlers survive, ours is added to both of its events.
        for event, groups in foreign["hooks"].items():
            self.assertTrue(all(g in after["hooks"][event] for g in groups), event)
        self.assertEqual(len(after["hooks"]["UserPromptSubmit"]), 2)
        self.assertEqual(len(after["hooks"]["SessionStart"]), 2)
        self.assertEqual(after["hooks"]["PreToolUse"], foreign["hooks"]["PreToolUse"])

        ours = [g for g in after["hooks"]["SessionStart"] if g not in foreign["hooks"]["SessionStart"]]
        self.assertEqual(len(ours), 1)
        matcher = ours[0]["matcher"]
        self.assertEqual(
            matcher, "^(" + "|".join(route.SESSION_START_SOURCES) + ")$",
            "installed matcher drifted from route.SESSION_START_SOURCES")
        handler = ours[0]["hooks"][0]
        self.assertEqual(handler["timeout"], 3, "a missing timeout can hang a turn")
        self.assertIn("--owner", handler["command"])

        # The deployed copy must be byte-identical to the reviewed source.
        deployed = re.findall(r"(\S+route\.py)", handler["command"])
        self.assertEqual(len(deployed), 1, handler["command"])
        self.assertEqual(Path(deployed[0]).read_bytes(), (HOOKS / "route.py").read_bytes())
        self.assertIn("DISARMED = True", Path(deployed[0]).read_text())

        # A second install changes nothing.
        again = self.install(config, skills, "--enable-interception")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(again.stdout.strip(), "Unchanged")

        # Removal needs no flag and restores the file byte for byte.
        gone = self.install(config, skills, "--remove")
        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertEqual((config / "hooks.json").read_bytes(), before)

    def test_remove_on_an_untouched_config_leaves_it_alone(self):
        foreign = {"hooks": {"UserPromptSubmit": [
            {"hooks": [{"type": "command", "command": "echo mine"}]}]}}
        config, skills = self.config(foreign), self.skills()
        before = (config / "hooks.json").read_bytes()
        done = self.install(config, skills, "--remove")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((config / "hooks.json").read_bytes(), before)

    def test_a_malformed_config_is_refused_without_being_rewritten(self):
        for existing in ({"unknown": 1}, {"hooks": []}, {"hooks": {"UserPromptSubmit": {}}},
                         {"hooks": {"UserPromptSubmit": [{"hooks": "no"}]}}):
            with self.subTest(existing=existing):
                config, skills = self.config(existing), self.skills()
                before = (config / "hooks.json").read_bytes()
                done = self.install(config, skills, "--enable-interception")
                self.assertEqual(done.returncode, 1, done.stdout)
                self.assertEqual((config / "hooks.json").read_bytes(), before)

    def test_a_backup_of_the_previous_config_is_kept(self):
        foreign = {"hooks": {"UserPromptSubmit": [
            {"hooks": [{"type": "command", "command": "echo mine"}]}]}}
        config, skills = self.config(foreign), self.skills()
        before = (config / "hooks.json").read_bytes()
        self.assertEqual(self.install(config, skills, "--enable-interception").returncode, 0)
        backups = list(config.glob("hooks.json.backup-*"))
        self.assertEqual(len(backups), 1, backups)
        self.assertEqual(backups[0].read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
