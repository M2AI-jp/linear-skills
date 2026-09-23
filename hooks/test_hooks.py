import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import install
import route


class HooksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.skills = self.root / 'skills'
        (self.skills / 'linear').mkdir(parents=True)
        (self.skills / 'linear' / 'SKILL.md').write_text('entry')
        self.work = self.root / 'work'
        self.work.mkdir()
        self.config = self.root / 'config'

    def run_route(self, data, *args):
        result = subprocess.run([sys.executable, str(Path(route.__file__)), '--skills-root', str(self.skills), *args], input=data, capture_output=True, timeout=2)
        self.assertEqual(result.returncode, 0)
        return result.stdout

    def event(self, **overrides):
        return dict(hook_event_name='UserPromptSubmit', prompt='Linearの計画を進める', cwd=str(self.work), **overrides)

    def test_prompt_context_only(self):
        output = json.loads(self.run_route(json.dumps(self.event()).encode()))
        self.assertEqual(set(output), {'hookSpecificOutput'})
        self.assertEqual(set(output['hookSpecificOutput']), {'hookEventName', 'additionalContext'})
        self.assertIn('OFF', output['hookSpecificOutput']['additionalContext'])
        self.assertIn('読取だけ', output['hookSpecificOutput']['additionalContext'])

    def test_parent_context_and_resume(self):
        (self.work / 'AGENTS.md').write_text('Project: https://linear.app/example')
        sub = self.work / 'sub'
        sub.mkdir()
        for event in ('UserPromptSubmit', 'SessionStart'):
            payload = dict(hook_event_name=event, prompt='続けて', cwd=str(sub), source='resume')
            self.assertIsNotNone(route.context(payload, self.skills))
        payload['source'] = 'compact'
        self.assertIsNotNone(route.context(payload, self.skills))
        payload['source'] = 'startup'
        self.assertIsNone(route.context(payload, self.skills))

    def test_fifo_is_nonblocking(self):
        payload = self.event()
        payload['prompt'] = '続けて'
        os.mkfifo(self.work / 'AGENTS.md')
        self.assertEqual(self.run_route(json.dumps(payload).encode()), b'')

    def test_unrelated_and_out_of_scope(self):
        for event in ('Stop', 'PreToolUse', 'SessionEnd', 'unknown'):
            payload = self.event()
            payload['hook_event_name'] = event
            self.assertIsNone(route.context(payload, self.skills))
        payload = self.event()
        payload['prompt'] = '晩ごはん'
        self.assertIsNone(route.context(payload, self.skills))

    def test_bad_input_never_blocks(self):
        for data in (b'{', b'null', b'[]', b'{}', b'\xff', b'x' * (route.LIMIT + 1)):
            self.assertEqual(self.run_route(data), b'')
        (self.skills / 'linear' / 'SKILL.md').unlink()
        self.assertEqual(self.run_route(json.dumps(self.event()).encode()), b'')

    def test_bad_agent_files_and_symlinks(self):
        payload = self.event()
        payload['prompt'] = '続けて'
        agent = self.work / 'AGENTS.md'
        for content in (b'\xff', b'x' * (route.LIMIT + 1)):
            agent.write_bytes(content)
            self.assertEqual(self.run_route(json.dumps(payload).encode()), b'')
        agent.unlink()
        agent.symlink_to(self.skills / 'linear' / 'SKILL.md')
        self.assertEqual(self.run_route(json.dumps(payload).encode()), b'')

    def test_merge_idempotence_update_remove(self):
        self.config.mkdir()
        other = {'type': 'command', 'command': 'echo existing'}
        original = {'description': 'keep', 'hooks': {'UserPromptSubmit': [{'hooks': [other]}], 'Stop': [{'hooks': [other]}]}}
        target = self.config / 'hooks.json'
        target.write_text(json.dumps(original))
        initial = target.read_bytes()
        install.install(self.config, self.skills)
        first = target.read_bytes()
        saved = json.loads(first)
        self.assertEqual(saved['hooks']['Stop'], original['hooks']['Stop'])
        self.assertEqual(saved['hooks']['UserPromptSubmit'][0], original['hooks']['UserPromptSubmit'][0])
        self.assertEqual(install.install(self.config, self.skills), 'Unchanged')
        self.assertEqual(target.read_bytes(), first)
        source = self.root / 'updated.py'
        source.write_bytes(Path(route.__file__).read_bytes() + b'\n# next version\n')
        install.install(self.config, self.skills, source=source)
        self.assertNotEqual(target.read_bytes(), first)
        self.assertEqual(len(json.loads(target.read_bytes())['hooks']['UserPromptSubmit']), 2)
        install.install(self.config, self.skills, remove=True)
        removed = json.loads(target.read_bytes())
        self.assertEqual(removed['hooks']['UserPromptSubmit'], original['hooks']['UserPromptSubmit'])
        self.assertEqual(removed['hooks']['SessionStart'], [])
        self.assertEqual(removed['hooks']['Stop'], original['hooks']['Stop'])
        self.assertEqual(install.install(self.config, self.skills, remove=True), 'Unchanged')
        self.assertIn(initial, [p.read_bytes() for p in self.config.glob('hooks.json.backup-*')])


    def test_symlink_reads_and_missing_script_repair(self):
        linked = self.root / 'linked-skills'
        linked.symlink_to(self.skills, target_is_directory=True)
        self.assertIsNotNone(route.context(self.event(), linked))
        actual = self.root / 'actual-agent.md'
        actual.write_text('Linear project')
        (self.work / 'AGENTS.md').symlink_to(actual)
        payload = self.event()
        payload['prompt'] = '続けて'
        self.assertIsNotNone(route.context(payload, linked))
        install.install(self.config, linked)
        target = self.config / 'hooks.json'
        before = target.read_bytes()
        script = next((self.config / 'linear-harness').glob('*/route.py'))
        script.unlink()
        self.assertIn('Restored', install.install(self.config, linked))
        self.assertTrue(script.is_file())
        self.assertEqual(target.read_bytes(), before)
        (self.work / 'AGENTS.md').unlink()
        (self.work / 'AGENTS.md').symlink_to(self.work / 'AGENTS.md')
        self.assertEqual(self.run_route(json.dumps(payload).encode()), b'')

    def test_invalid_config_unchanged(self):
        self.config.mkdir()
        target = self.config / 'hooks.json'
        for data in (b'{', b'{"hooks":[]}', b'{"unknown":true}', b'{"hooks":{"Stop":[{}]}}'):
            target.write_bytes(data)
            with self.assertRaises(ValueError):
                install.install(self.config, self.skills)
            self.assertEqual(target.read_bytes(), data)
        target.unlink()
        target.symlink_to(self.skills / 'linear' / 'SKILL.md')
        with self.assertRaises(ValueError):
            install.install(self.config, self.skills)
        self.assertEqual((self.skills / 'linear' / 'SKILL.md').read_text(), 'entry')

    def test_installed_command_runs_and_missing_entry_preserves_config(self):
        install.install(self.config, self.skills)
        target = self.config / 'hooks.json'
        before = target.read_bytes()
        command = json.loads(before)['hooks']['UserPromptSubmit'][0]['hooks'][0]['command']
        result = subprocess.run(command, shell=True, input=json.dumps(self.event()), text=True, capture_output=True, timeout=2)
        self.assertEqual(result.returncode, 0)
        self.assertIn('additionalContext', result.stdout)
        (self.skills / 'linear' / 'SKILL.md').unlink()
        with self.assertRaises((ValueError, OSError)):
            install.install(self.config, self.skills)
        self.assertEqual(target.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
