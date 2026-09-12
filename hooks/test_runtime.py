"""Protocol/transition regression checks; these do not certify business semantics."""
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runtime
from linear_read import Unavailable, equivalent, project_issues, complete_nodes, state as resolve_state

PROJECT = "11111111-1111-1111-1111-111111111111"
DATA = {"project": {"id": PROJECT, "name": "current", "url": "https://linear.app/current",
        "content": "現在の要求", "updatedAt": "now", "status": {"id": "s", "name": "In Progress"},
        "teams": {"nodes": [{"id": "team-a", "name": "Team A", "key": "T"}]}},
        "workflowStates": {"nodes": [{"id": "d", "name": "Done", "type": "completed"},
          {"id": "t", "name": "Todo", "type": "unstarted"},
          {"id": "r", "name": "In Review", "type": "started"},
          {"id": "p", "name": "In Progress", "type": "started"}]},
        "projectStatuses": {"nodes": [{"id": "c", "name": "Completed", "type": "completed"},
          {"id": "s", "name": "In Progress", "type": "started"}]}}
ISSUE = {"id": "x", "identifier": "TEST-1", "title": "入力を引き継ぐ",
         "description": "受け手が実際に使える", "project": {"id": PROJECT},
         "team": {"id": "team-a"},
         "state": {"id": "r", "name": "In Review", "type": "started"},
         "inverseRelations": {"nodes": [], "pageInfo": {"hasNextPage": False}}}
for workflow in DATA['workflowStates']['nodes']:
    workflow['teamId'] = 'team-a'

def project_row(identifier="TEST-1", state="completed", labels=(), blockers=()):
    return {"identifier": identifier, "state": {"type": state},
            "labels": {"nodes": [{"name": name} for name in labels],
                       "pageInfo": {"hasNextPage": False}},
            "inverseRelations": {"nodes": [
                {"type": "blocks", "issue": {"identifier": name, "state": {"type": kind}}}
                for name, kind in blockers], "pageInfo": {"hasNextPage": False}}}

class BindingTests(unittest.TestCase):
    def test_native_agents_without_git_or_ssot_and_bootstrap(self):
        with tempfile.TemporaryDirectory() as folder, patch("runtime.ROOT", Path(folder)):
            entry = Path(folder) / "AGENTS.md"
            entry.write_text("Linear Project ID: " + PROJECT + "\n")
            self.assertEqual(runtime.binding(), PROJECT)
            entry.write_text("Linear Project ID: 未作成\n")
            self.assertIsNone(runtime.binding())
            self.assertEqual(runtime.before({"tool_name": "mcp__linear__save_project",
                                            "tool_input": {"name": "new"}}), {})

    def test_existing_ssot_and_conflicting_or_invalid_entries(self):
        with tempfile.TemporaryDirectory() as folder, patch("runtime.ROOT", Path(folder)):
            root = Path(folder)
            with self.assertRaises(Unavailable):
                runtime.binding()
            (root / "SSOT.md").write_text("Linear Project ID: " + PROJECT + "\n")
            self.assertEqual(runtime.binding(), PROJECT)
            (root / "AGENTS.md").write_text("Linear Project ID: " + PROJECT + "\n")
            self.assertEqual(runtime.binding(), PROJECT)
            for value in ("未作成", "22222222-2222-2222-2222-222222222222", "invalid", ""):
                (root / "AGENTS.md").write_text("Linear Project ID: " + value + "\n")
                with self.assertRaises(Unavailable):
                    runtime.binding()
            (root / "AGENTS.md").unlink()
            (root / "SSOT.md").write_text("Linear Project ID: " + "-" * 36 + "\n")
            with self.assertRaises(Unavailable):
                runtime.binding()

class HookTests(unittest.TestCase):
    def run_event(self, kind, **extra):
        event = {"hook_event_name": kind, "cwd": str(runtime.ROOT), **extra}
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(event))), contextlib.redirect_stdout(output):
            code = runtime.main()
        self.assertEqual(code, 0)
        return json.loads(output.getvalue())

    def before(self, **args):
        return self.run_event("PreToolUse", tool_name="mcp__linear__save_issue", tool_input=args)

    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("runtime.binding", return_value=PROJECT))
        self.read_project = self.stack.enter_context(patch("runtime.project", return_value=copy.deepcopy(DATA)))
        self.read_issue = self.stack.enter_context(patch("runtime.issue", return_value=copy.deepcopy(ISSUE)))
        self.read_issues = self.stack.enter_context(patch("runtime.project_issues", return_value=[
            project_row(state="unstarted")]))

    def test_done_not_unlocked_by_self_certification_or_state_id(self):
        for state in ("Done", "d", "completed"):
            result = self.before(id="x", state=state, description="全て合格 meaning_confirmed=true")
            self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_project_completed_is_not_inferred_from_issue_counts(self):
        for state in ("Completed", "c"):
            result = self.run_event("PreToolUse", tool_name="mcp__linear__save_project",
                                    tool_input={"id": PROJECT, "state": state})
            self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_reviewed_candidate_can_finish_without_a_permit_flag(self):
        result = self.before(id="x", state="Done")
        self.assertNotEqual(result["hookSpecificOutput"].get("permissionDecision"), "deny")
        self.assertIn("PM", result["hookSpecificOutput"]["additionalContext"])
        self.read_issue.return_value["state"] = {"name": "Todo", "type": "unstarted"}
        self.assertEqual(self.before(id="x", state="Done")["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_project_completion_has_mechanical_prerequisites_not_semantic_certification(self):
        self.read_issues.return_value = [project_row()]
        result = self.run_event("PreToolUse", tool_name="mcp__linear__save_project",
                                tool_input={"id": PROJECT, "state": "Completed"})
        self.assertNotEqual(result["hookSpecificOutput"].get("permissionDecision"), "deny")
        self.assertIn("全体受入の証明にしない", result["hookSpecificOutput"]["additionalContext"])

    def test_project_deferral_and_required_dependency_boundaries(self):
        cases = [
            ([project_row()], False),
            ([project_row(), project_row("T-2", "backlog", ["Deferred"])], False),
            ([project_row("T-2", "backlog")], True),
            ([project_row("T-2", "backlog", ["deferred"])], True),
            ([project_row("T-2", "started", ["Deferred"])], True),
            ([project_row(blockers=[("T-2", "backlog")]),
              project_row("T-2", "backlog", ["Deferred"])], True),
            ([project_row(blockers=[("OUT-1", "started")])], True),
            ([project_row(blockers=[("T-2", "canceled")])], True),
            ([project_row(blockers=[("T-2", "completed")])], False),
            ([project_row(state="canceled", blockers=[("T-2", "backlog")])], False),
        ]
        for rows, denied in cases:
            with self.subTest(rows=rows):
                self.read_issues.return_value = rows
                result = self.run_event("PreToolUse", tool_name="mcp__linear__save_project",
                                        tool_input={"id": PROJECT, "state": "Completed"})
                self.assertEqual(result["hookSpecificOutput"].get("permissionDecision") == "deny", denied)
        self.read_issues.return_value = [project_row("T-2", "backlog", ["Deferred"])]
        result = self.run_event("PreToolUse", tool_name="mcp__linear__save_project",
                                tool_input={"id": PROJECT, "state": "Completed", "description": "new scope"})
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_deferred_label_creation_is_limited_to_current_team_and_new_name(self):
        for method in ("save_issue_label", "create_issue_label"):
            good = {"teamId": "team-a", "name": "Deferred"}
            self.assertEqual(self.run_event("PreToolUse", tool_name="mcp__linear__" + method,
                                           tool_input=good), {})
            for extra in ({"id": "existing"}, {"teamId": "team-b"}, {"teamId": None},
                          {"name": "deferred"}, {"name": "Other"}, {"isGroup": True}):
                with self.subTest(method=method, extra=extra):
                    result = self.run_event("PreToolUse", tool_name="mcp__linear__" + method,
                                            tool_input={**good, **extra})
                    self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_project_issue_metadata_incomplete_never_allows_completion(self):
        broken = []
        for field in ("labels", "inverseRelations"):
            for kind in ("missing", "page", "truncated", "nodes"):
                row = project_row(state="backlog", labels=["Deferred"])
                if kind == "missing":
                    del row[field]
                elif kind == "page":
                    del row[field]["pageInfo"]
                elif kind == "truncated":
                    row[field]["pageInfo"]["hasNextPage"] = True
                else:
                    row[field]["nodes"] = [{}]
                broken.append(row)
        row = project_row()
        del row["state"]
        broken.append(row)
        for row in broken:
            with self.subTest(row=row):
                payload = {"project": {"issues": {"nodes": [row],
                           "pageInfo": {"hasNextPage": False}}}}
                with patch("linear_read.query", return_value=payload):
                    with self.assertRaises(Unavailable):
                        project_issues(PROJECT)
                    self.read_issues.side_effect = project_issues
                    result = self.run_event("PreToolUse", tool_name="mcp__linear__save_project",
                                            tool_input={"id": PROJECT, "state": "Completed"})
                    self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        for info in ({}, {"hasNextPage": None}, {"hasNextPage": 0}):
            with patch("linear_read.query", return_value={"project": {"issues": {
                    "nodes": [project_row()], "pageInfo": info}}}), self.assertRaises(Unavailable):
                project_issues(PROJECT)

    def test_reads_remain_possible_during_api_failure(self):
        self.read_project.side_effect = Unavailable("offline")
        self.assertEqual(self.run_event("PreToolUse", tool_name="mcp__linear__get_project",
                                       tool_input={"query": PROJECT}), {})
        self.read_project.assert_not_called()
        self.assertEqual(self.before(id="x", state="Todo")["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_start_fetches_remote_context_each_time(self):
        self.run_event("SessionStart", source="resume")
        self.run_event("SessionStart", source="compact")
        self.assertEqual(self.read_project.call_count, 2)

    def test_reopen_and_normal_work_are_allowed(self):
        for state in ("Todo", "In Progress", "In Review"):
            self.assertEqual(self.before(id="x", state=state), {})

    def test_unfinished_or_canceled_dependency_blocks_start_but_not_repair(self):
        for kind in ("unstarted", "canceled"):
            self.read_issue.return_value["inverseRelations"]["nodes"] = [
                {"type": "blocks", "issue": {"identifier": "TEST-0", "state": {"type": kind}}}]
            self.assertEqual(self.before(id="x", state="In Progress")["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertEqual(self.before(id="x", state="Todo"), {})

    def test_wrong_project_and_duplicate_project_creation_are_denied(self):
        self.read_issue.return_value["project"]["id"] = "other"
        self.assertEqual(self.before(id="x", state="Todo")["hookSpecificOutput"]["permissionDecision"], "deny")
        result = self.run_event("PreToolUse", tool_name="mcp__linear__save_project", tool_input={"name": "duplicate"})
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_foreign_reads_and_unscoped_searches_do_not_reach_the_model(self):
        for method, args in (("get_project", {"query": "other"}), ("list_projects", {}),
                             ("list_issues", {}), ("list_documents", {})):
            result = self.run_event("PreToolUse", tool_name="mcp__linear__" + method, tool_input=args)
            self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.read_issue.return_value["project"]["id"] = "other"
        result = self.run_event("PreToolUse", tool_name="mcp__linear__get_issue", tool_input={"id": "x"})
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        result = self.run_event("PreToolUse", tool_name="Bash", tool_input={
            "command": 'linear-api --query \'query { project(id: "foreign") { id content } }\''})
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_new_issue_uses_the_explicit_team_workflow(self):
        self.read_project.return_value['workflowStates']['nodes'].append(
            {'id': 'other-todo', 'name': 'Todo', 'type': 'unstarted', 'teamId': 'team-b'})
        self.assertEqual(self.before(project=PROJECT, team='team-a', state='Todo', title='new'), {})
        self.assertEqual(self.before(project=PROJECT, team='unknown', state='Todo')["hookSpecificOutput"]["permissionDecision"], 'deny')

    def test_project_state_is_read_back_after_completion_and_reopening(self):
        for desired, actual_id in [('Completed', 's'), ('In Progress', 'c')]:
            self.read_project.return_value['project']['status']['id'] = actual_id
            result = self.run_event('PostToolUse', tool_name='mcp__linear__save_project',
                                   tool_input={'id': PROJECT, 'state': desired}, tool_response={'id': PROJECT})
            self.assertIn('状態の読み戻しが一致しません', result['systemMessage'])
        self.read_project.return_value['project']['status'] = {'id': 'c', 'name': 'Completed'}
        result = self.run_event('PostToolUse', tool_name='mcp__linear__save_project',
                               tool_input={'id': PROJECT, 'state': 'Completed'}, tool_response={'id': PROJECT})
        self.assertNotIn('systemMessage', result)

    def test_done_reopens_even_when_its_prerequisite_has_failed(self):
        self.read_issue.return_value["state"] = {"name": "Done", "type": "completed"}
        self.read_issue.return_value["inverseRelations"]["nodes"] = [
            {"type": "blocks", "issue": {"identifier": "TEST-0", "state": {"type": "unstarted"}}}]
        self.assertEqual(self.before(id="x", state="In Review"), {})
        self.assertEqual(self.before(id="x", description="changed acceptance")["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_partial_repair_cannot_start_downstream_work(self):
        self.read_issue.return_value["description"] = "The source was corrected, adoption is still under review."
        self.read_issue.return_value["inverseRelations"]["nodes"] = [
            {"type": "blocks", "issue": {"identifier": "TEST-0", "state": {"type": "started"}}}]
        self.assertEqual(self.before(id="x", state="In Progress")["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(self.before(id="x", state="Done")["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(self.before(id="x", state="Todo"), {})

    def test_bootstrap_allows_one_new_project_not_old_edits(self):
        with patch("runtime.binding", return_value=None):
            self.assertEqual(self.run_event("PreToolUse", tool_name="mcp__linear__save_project",
                                           tool_input={"name": "new", "state": "In Progress"}), {})
            result = self.run_event("PreToolUse", tool_name="mcp__linear__save_project",
                                    tool_input={"id": "old", "description": "reuse"})
            self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_milestone_creation_in_current_project_is_allowed(self):
        self.assertEqual(self.run_event("PreToolUse", tool_name="mcp__linear__save_milestone",
                                       tool_input={"project": PROJECT, "name": "usable"}), {})

    def test_foreign_milestone_cannot_be_read_or_attached_to_current_issue(self):
        with patch('runtime.resource', return_value={'project': {'id': 'other'}}):
            result = self.run_event('PreToolUse', tool_name='mcp__linear__get_milestone',
                                   tool_input={'project': PROJECT, 'query': PROJECT})
            self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')
            result = self.before(id='x', milestone=PROJECT)
            self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')
        with patch('runtime.resource', return_value={'project': {'id': PROJECT}}):
            self.assertEqual(self.before(id='x', milestone=PROJECT), {})

    def test_partial_write_warns_and_does_not_retry(self):
        result = self.run_event("PostToolUse", tool_name="mcp__linear__save_issue",
                    tool_input={"id": "x", "description": "new"},
                    tool_response={"content": [{"type": "text", "text": '{"id":"x"}'}]})
        self.assertIn("一致しません", result["systemMessage"])
        self.read_issue.assert_called_once_with("x")

    def test_error_response_cannot_become_success(self):
        result = self.run_event("PostToolUse", tool_name="mcp__linear__save_issue",
                               tool_input={"id": "x"}, tool_response={"isError": True})
        self.assertIn("部分反映", result["systemMessage"])
        self.read_issue.assert_not_called()

    def test_main_merge_and_explicit_direct_mutation_are_denied(self):
        for command in ("git push origin HEAD:main",
                        "linear-api --query 'mutation { anything }'",
                        "curl https://api.linear.app/graphql -d '{}'" ):
            result = self.run_event("PreToolUse", tool_name="Bash", tool_input={"command": command})
            self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_git_branch_direction_controls_the_write_target(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(["git", "init", "-q", "-b", "main", directory], check=True)
            result = self.run_event("PreToolUse", tool_name="Bash",
                                   tool_input={"command": "git merge codex/candidate", "workdir": directory})
            self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
            subprocess.run(["git", "-C", directory, "switch", "-q", "-c", "codex/work"], check=True)
            self.assertEqual(self.run_event("PreToolUse", tool_name="Bash",
                             tool_input={"command": "git merge main", "workdir": directory}), {})

    def test_rendering_differences_are_distinct_from_changed_link_targets(self):
        actual = '* source [MAT-1](https://linear.app/work/issue/MAT-1/title)\n\n| -- | -- |'
        self.assertTrue(equivalent(actual, '- source MAT-1\n|---|---|'))
        self.assertFalse(equivalent('[source](https://wrong.example)', '[source](https://right.example)'))
        self.assertFalse(equivalent('[MAT-1](https://linear.app/wrong/issue/MAT-1/a)',
                                    '[MAT-1](https://linear.app/right/issue/MAT-1/a)'))
        self.assertFalse(equivalent('[x](https://example/a%2Fb)', '[x](https://example/a/b)'))
        self.assertFalse(equivalent('[x](https://example/?q=a%26b)', '[x](https://example/?q=a&b)'))
        self.assertTrue(equivalent('[x](https://example/%E3%81%82)', '[x](https://example/あ)'))

    def test_pages_are_read_to_completion_and_stalled_cursor_fails(self):
        first = {"project": {"issues": {"nodes": [project_row("T-1")],
                  "pageInfo": {"hasNextPage": True, "endCursor": "cursor"}}}}
        last = {"project": {"issues": {"nodes": [project_row("T-2")],
                 "pageInfo": {"hasNextPage": False, "endCursor": "end"}}}}
        with patch('linear_read.query', side_effect=[first, last]) as read:
            self.assertEqual(len(project_issues(PROJECT)), 2)
            self.assertEqual(read.call_args.args[1]['after'], 'cursor')
        with patch('linear_read.query', return_value=first), self.assertRaises(Unavailable):
            project_issues(PROJECT)
        with self.assertRaises(Unavailable):
            complete_nodes(first['project']['issues'])

    def test_ambiguous_workflow_and_generic_started_are_not_guessed(self):
        with self.assertRaises(Unavailable):
            resolve_state('started', DATA['workflowStates']['nodes'])
        with self.assertRaises(Unavailable):
            resolve_state('Done', [DATA['workflowStates']['nodes'][0]] * 2)

    def test_readonly_stop_does_not_continue_and_old_turn_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transcript.jsonl"
            rows = [{"type": "event_msg", "payload": {"type": "task_started", "turn_id": "old"}},
                    {"type": "response_item", "payload": {"name": "apply_patch"}},
                    {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "now"}}]
            path.write_text("\n".join(json.dumps(r) for r in rows))
            self.assertEqual(self.run_event("Stop", turn_id="now", transcript_path=str(path)), {})
            rows.append({"type": "response_item", "payload": {"name": "apply_patch"}})
            path.write_text("\n".join(json.dumps(r) for r in rows))
            self.assertEqual(self.run_event("Stop", turn_id="now", transcript_path=str(path))["decision"], "block")
            self.assertEqual(self.run_event("Stop", turn_id="now", transcript_path=str(path),
                                           stop_hook_active=True), {})

    def test_hook_prompt_is_not_reintroduced_as_user_requirement(self):
        self.assertEqual(self.run_event("UserPromptSubmit", prompt=runtime.MARK + " retry"), {})

    def test_stop_uses_current_native_completed_mcp_items(self):
        # Codex 0.153.4 records code-mode MCP calls here, not as function_call.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transcript.jsonl"
            for tool, turn, expected in (("get_issue", "now", False),
                                         ("save_issue", "old", False),
                                         ("save_issue", "now", True),
                                         ("save_project", "now", True)):
                with self.subTest(tool=tool, turn=turn):
                    row = {"type": "event_msg", "payload": {
                        "type": "item_completed", "turn_id": turn,
                        "item": {"type": "McpToolCall", "server": "linear",
                                 "tool": tool, "status": "completed"}}}
                    path.write_text(json.dumps(row) + "\n")
                    result = self.run_event("Stop", turn_id="now", transcript_path=str(path))
                    self.assertEqual(result.get("decision") == "block", expected)
                    self.assertEqual(self.run_event("Stop", turn_id="now", transcript_path=str(path),
                                                     stop_hook_active=True), {})

    def test_stop_distinguishes_pre_execution_denial_from_uncertain_write_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transcript.jsonl"
            for message, expected in (("MCP tool call requires approval, but approval policy is never", False),
                                      ("MCP request timed out", True)):
                with self.subTest(message=message):
                    row = {"type": "event_msg", "payload": {
                        "type": "item_completed", "turn_id": "now",
                        "item": {"type": "McpToolCall", "server": "linear", "tool": "save_issue",
                                 "status": "failed", "error": {"message": message}, "result": None}}}
                    path.write_text(json.dumps(row) + "\n")
                    result = self.run_event("Stop", turn_id="now", transcript_path=str(path))
                    self.assertEqual(result.get("decision") == "block", expected)

    def test_post_tool_reads_back_native_flat_issue_response_with_project_name(self):
        response = {"content": [{"type": "text", "text": json.dumps({
            "id": "TEST-1", "project": "current", "status": "In Review"})}]}
        result = self.run_event("PostToolUse", tool_name="mcp__linear__save_issue",
                                tool_input={"id": "TEST-1", "state": "In Review"},
                                tool_response=response)
        self.read_issue.assert_called_once_with("TEST-1")
        self.assertIn("TEST-1を再取得", result["hookSpecificOutput"]["additionalContext"])

    def test_quoted_documentation_is_not_treated_as_an_operation(self):
        self.assertEqual(self.run_event("PreToolUse", tool_name="Bash",
                         tool_input={"command": "printf '%s' 'git merge main'"}), {})

    def test_invalid_tool_input_is_denied(self):
        result = self.run_event("PreToolUse", tool_name="mcp__linear__save_issue", tool_input="invalid")
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_malformed_protocol_fails_with_exit_two(self):
        proc = subprocess.run([sys.executable, str(runtime.ROOT / "hooks/runtime.py")],
                              input="broken", capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("permissionDecision", proc.stdout)

class GitIntegrationTests(unittest.TestCase):
    SHA = "a" * 40
    BASE = "b" * 40

    def setUp(self):
        self.reader = runtime.github_read
        self.pr = {"state": "open", "draft": False, "mergeable": True,
                   "mergeable_state": "clean", "head": {"sha": self.SHA},
                   "base": {"ref": "main", "sha": self.BASE,
                            "repo": {"full_name": "owner/repo"}},
                   "merged": True, "merge_commit_sha": "c" * 40}
        self.protection = {"required_status_checks": {"strict": True,
            "contexts": ["qa"], "checks": [{"context": "qa", "app_id": 1}]},
            "enforce_admins": {"enabled": True}}
        self.runs = [{"id": 1, "name": "qa", "app": {"id": 1}, "head_sha": self.SHA,
                      "status": "completed", "conclusion": "success"}]

    def api(self, path):
        if "/pulls/" in path:
            return copy.deepcopy(self.pr)
        if "/rules/branches/" in path:
            return []
        if path.endswith("/protection"):
            return self.protection
        if "/branches/" in path:
            return {"commit": {"sha": self.BASE}}
        if "/compare/" in path:
            return {"status": "ahead"}
        if "/check-runs?" in path:
            return {"check_runs": self.runs, "total_count": len(self.runs)}
        self.fail(path)

    def validate(self):
        self.reader.validate_merge("owner/repo", "1", self.SHA)

    def test_native_protection_checks_and_post_merge_mapping(self):
        with patch.object(self.reader, "api", side_effect=self.api):
            self.validate()
            self.assertEqual(self.reader.verify_merge("owner/repo", "1", self.SHA),
                             ("c" * 40, self.BASE))

    def test_required_latest_sha_issuer_and_success(self):
        for field, value in (("conclusion", "neutral"), ("conclusion", "skipped"),
                             ("conclusion", "failure"), ("status", "in_progress"),
                             ("head_sha", self.BASE), ("app", {"id": 2})):
            with self.subTest(field=field, value=value):
                latest = copy.deepcopy(self.runs[0])
                latest.update(id=2)
                latest[field] = value
                self.runs = [latest] if field == "app" else [self.runs[0], latest]
                with patch.object(self.reader, "api", side_effect=self.api), self.assertRaises(Unavailable):
                    self.validate()
                self.setUp()

    def test_unknown_protection_and_stale_pr_refused(self):
        for mutate in (lambda: self.protection["required_status_checks"].update(strict=False),
                       lambda: self.protection["enforce_admins"].update(enabled=False),
                       lambda: self.protection["required_status_checks"]["checks"][0].update(app_id=-1),
                       lambda: self.pr["head"].update(sha=self.BASE),
                       lambda: self.pr["base"].update(ref="other")):
            mutate()
            with patch.object(self.reader, "api", side_effect=self.api), self.assertRaises(Unavailable):
                self.validate()
            self.setUp()

    def test_movement_during_inspection_and_unmerged_result_refused(self):
        def moving(path):
            result = self.api(path)
            if "/check-runs?" in path:
                self.pr["head"]["sha"] = self.BASE
            return result
        with patch.object(self.reader, "api", side_effect=moving), self.assertRaises(Unavailable):
            self.validate()
        self.setUp()
        self.pr["merged"] = False
        with patch.object(self.reader, "api", side_effect=self.api), self.assertRaises(Unavailable):
            self.reader.verify_merge("owner/repo", "1", self.SHA)

    def test_api_failure_is_not_permission(self):
        with patch.object(self.reader.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "")):
            with self.assertRaises(Unavailable):
                self.reader.api("repos/owner/repo")

    def test_canonical_sync_route_and_post_read(self):
        command = f"gh pr merge 1 --repo owner/repo --match-head-commit {self.SHA} --squash"
        with patch.object(self.reader, "validate_merge") as pre:
            self.assertEqual(runtime.shell_guard(command), {})
            pre.assert_called_once_with("owner/repo", "1", self.SHA)
        for extra in (" --admin", " --auto", " &", "; git status"):
            with self.assertRaises(Unavailable):
                runtime.shell_guard(command + extra)
        with patch.object(self.reader, "verify_merge", return_value=("c" * 40, self.BASE)) as post:
            runtime.after({"tool_name": "exec_command", "tool_input": {"cmd": command}})
            post.assert_called_once()

    def test_main_ref_context_changes_and_git_failure(self):
        for command in ("git branch -f main HEAD", "cd elsewhere && git commit -m x",
                        "git switch main\ngit reset --hard HEAD"):
            self.assertEqual(runtime.shell_guard(command)["hookSpecificOutput"]["permissionDecision"], "deny")
        with patch.object(runtime.subprocess, "run", return_value=subprocess.CompletedProcess([], 128, "")):
            with self.assertRaises(Unavailable):
                runtime.shell_guard("git commit -m x")
            self.assertEqual(runtime.shell_guard("git status"), {})

    def test_direct_github_mutations_and_known_reads(self):
        for command in ("gh api repos/owner/repo/pulls/1/merge -X PUT",
                        "gh api repos/owner/repo/git/refs/heads/main -X PATCH -f sha=x",
                        "gh api graphql -f 'query=mutation { mergePullRequest }'"):
            self.assertIn("deny", str(runtime.shell_guard(command)))
        self.assertEqual(runtime.shell_guard("gh api repos/owner/repo/git/refs/heads/main"), {})
        self.assertTrue(runtime.github_mutation("mcp__github__merge_pull_request", {}))
        self.assertFalse(runtime.github_mutation("mcp__github__get_pull_request", {}))
        self.assertFalse(runtime.github_mutation("mcp__gws__update_document", {}))

class RepairTests(unittest.TestCase):
    def test_inherited_gh_merge_options_cannot_bypass_pre_or_post(self):
        for command in ("gh pr --repo owner/repo merge 1 --admin --squash",
                        "gh --repo owner/repo pr merge 1 --admin",
                        "gh pr -Rowner/repo merge 1 --admin",
                        "gh pr --repo=owner/repo merge 1 --admin"):
            with self.subTest(command=command):
                with self.assertRaises(Unavailable):
                    runtime.shell_guard(command)
                with self.assertRaises(Unavailable):
                    runtime.after({"tool_name": "Bash", "tool_input": {"command": command}})
        self.assertEqual(runtime.shell_guard("gh pr --repo owner/repo view 1"), {})

    def test_force_switch_main_and_normal_feature(self):
        for command in ("git checkout -B main feature", "git switch -C main feature",
                        "git switch --force-create=master feature", "git checkout -Bmain feature"):
            self.assertIn("deny", str(runtime.shell_guard(command)))
        for command in ("git switch feature", "git checkout feature", "git switch -C feature main",
                        "git checkout -B feature main", "git branch --list"):
            self.assertEqual(runtime.shell_guard(command), {})

    def test_native_patch_repairs_conflicting_binding_but_not_unrelated_files(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runtime, "ROOT", Path(directory).resolve()):
            root = Path(directory)
            (root / "AGENTS.md").write_text("Linear Project ID: 未作成\n")
            (root / "SSOT.md").write_text(f"Linear Project ID: {PROJECT}\n")
            command = "*** Begin Patch\n*** Update File: AGENTS.md\n@@\n-Linear Project ID: 未作成\n+Linear Project ID: " + PROJECT + "\n*** End Patch"
            event = {"tool_name": "apply_patch", "cwd": directory, "tool_input": {"command": command}}
            self.assertEqual(runtime.before(event), {})
            (root / "AGENTS.md").write_text(f"Linear Project ID: {PROJECT}\n")
            self.assertEqual(runtime.binding(), PROJECT)
            with patch.object(runtime, "project", side_effect=Unavailable("deleted")):
                self.assertEqual(runtime.before(event), {})
                for invalid in (command.replace("AGENTS.md", "app.py"),
                                command.replace("AGENTS.md", "../AGENTS.md"),
                                command.replace("@@", "*** Move to: ../app.py\n@@"), "repair AGENTS.md"):
                    with self.assertRaises(Unavailable):
                        runtime.before({**event, "tool_input": {"command": invalid}})
                with self.assertRaises(Unavailable):
                    runtime.before({**event, "tool_input": {"input": command}})


class ProjectDeletionTests(unittest.TestCase):
    def setUp(self):
        self.module = runtime.linear_delete
        self.active = {"id": PROJECT, "name": "fixture", "trashed": False, "archivedAt": None}
        self.deleted = dict(self.active, trashed=True)

    def response(self, success=True):
        return subprocess.CompletedProcess([], 0, json.dumps({"data": {"projectDelete": {"success": success}}}))

    def test_mismatch_and_missing_target_never_write(self):
        with patch.object(self.module, "snapshot") as read, patch.object(self.module.subprocess, "run") as write:
            with self.assertRaises(Unavailable):
                self.module.delete_project("00000000-0000-0000-0000-000000000000", lambda: PROJECT)
            read.assert_not_called()
            write.assert_not_called()
        with patch.object(self.module, "query", return_value={"project": None}), \
                patch.object(self.module.subprocess, "run") as write:
            with self.assertRaises(Unavailable):
                self.module.delete_project(PROJECT, lambda: PROJECT)
            write.assert_not_called()

    def test_fixed_mutation_and_same_id_readback(self):
        with patch.object(self.module, "snapshot", side_effect=[self.active, self.deleted]) as read, \
                patch.object(self.module.subprocess, "run", return_value=self.response()) as write:
            self.assertEqual(self.module.delete_project(PROJECT, lambda: PROJECT)["result"], "deleted")
            self.assertEqual(read.call_args_list, [unittest.mock.call(PROJECT), unittest.mock.call(PROJECT)])
            write.assert_called_once()
            body = json.loads(write.call_args.kwargs["input"])
            self.assertEqual(body["variables"], {"id": PROJECT})
            self.assertEqual(body["query"], "mutation($id: String!) { projectDelete(id: $id) { success } }")

    def test_nullable_live_snapshot_can_be_deleted(self):
        live = dict(self.active, trashed=None)
        with patch.object(self.module, "query", return_value={"project": live}), \
                patch.object(runtime, "binding", return_value=PROJECT):
            self.assertEqual(runtime.shell_guard(f"python3 hooks/linear_delete.py {PROJECT}"), {})
        with patch.object(self.module, "query", side_effect=[{"project": live}, {"project": self.deleted}]) as read, \
                patch.object(self.module.subprocess, "run", return_value=self.response()) as write:
            self.assertEqual(self.module.delete_project(PROJECT, lambda: PROJECT)["result"], "deleted")
            self.assertEqual(read.call_count, 2)
            self.assertTrue(all(call.args[1] == {"id": PROJECT} for call in read.call_args_list))
            write.assert_called_once()

    def test_invalid_live_snapshot_never_writes(self):
        missing = {key: value for key, value in self.active.items() if key != "trashed"}
        invalid = [missing, dict(self.active, id="other")]
        invalid.extend(dict(self.active, trashed=value) for value in ("true", "false", 0, 1, [], {}))
        for actual in invalid:
            with self.subTest(actual=actual), \
                    patch.object(self.module, "query", return_value={"project": actual}), \
                    patch.object(self.module.subprocess, "run") as write:
                with self.assertRaises(Unavailable):
                    self.module.delete_project(PROJECT, lambda: PROJECT)
                write.assert_not_called()

    def test_unconfirmed_readback_never_repeats_write(self):
        missing = {key: value for key, value in self.active.items() if key != "trashed"}
        invalid = [missing, dict(self.deleted, id="other")]
        invalid.extend(dict(self.active, trashed=value) for value in (None, False, "true", "false", 0, 1, [], {}))
        for actual in invalid:
            with self.subTest(actual=actual), \
                    patch.object(self.module, "query", side_effect=[
                        {"project": dict(self.active, trashed=None)}, {"project": actual}]) as read, \
                    patch.object(self.module.subprocess, "run", return_value=self.response()) as write:
                with self.assertRaises(Unavailable):
                    self.module.delete_project(PROJECT, lambda: PROJECT)
                self.assertEqual(read.call_count, 2)
                write.assert_called_once()

    def test_partial_failure_archive_and_timeout_are_not_success(self):
        for response, actual in ((self.response(), self.active),
                                 (self.response(), dict(self.active, archivedAt="date")),
                                 (self.response(False), self.deleted),
                                 (subprocess.TimeoutExpired("linear-api", 12), self.deleted)):
            with self.subTest(response=response, actual=actual):
                with patch.object(self.module, "snapshot", side_effect=[self.active, actual]) as read, \
                        patch.object(self.module.subprocess, "run") as write:
                    if isinstance(response, Exception):
                        write.side_effect = response
                    else:
                        write.return_value = response
                    with self.assertRaises(Unavailable):
                        self.module.delete_project(PROJECT, lambda: PROJECT)
                    self.assertEqual(read.call_count, 2)
                    write.assert_called_once()

    def test_already_deleted_does_not_repeat_mutation(self):
        with patch.object(self.module, "snapshot", return_value=self.deleted), \
                patch.object(self.module.subprocess, "run") as write:
            self.assertEqual(self.module.delete_project(PROJECT, lambda: PROJECT)["result"], "already_deleted")
            write.assert_not_called()

    def test_native_entry_changed_before_write(self):
        with patch.object(self.module, "snapshot", return_value=self.active), \
                patch.object(self.module.subprocess, "run") as write:
            entries = iter([PROJECT, None])
            with self.assertRaises(Unavailable):
                self.module.delete_project(PROJECT, lambda: next(entries))
            write.assert_not_called()

    def test_hook_scopes_command_and_reads_actual_deletion(self):
        command = f"python3 hooks/linear_delete.py {PROJECT}"
        with patch.object(runtime, "binding", return_value=PROJECT), \
                patch.object(self.module, "snapshot", return_value=self.deleted) as read:
            self.assertEqual(runtime.shell_guard(command), {})
            runtime.after({"tool_name": "Bash", "tool_input": {"command": command}})
            self.assertEqual(read.call_count, 2)
            for invalid in (command + " extra", command + " &", "cd elsewhere && " + command,
                            command.replace("hooks/", "elsewhere/"),
                            command.replace(PROJECT, "00000000-0000-0000-0000-000000000000")):
                with self.assertRaises(Unavailable):
                    runtime.shell_guard(invalid)
            self.assertIn("deny", str(runtime.shell_guard("linear-api --query mutation")))

if __name__ == "__main__":
    unittest.main()
