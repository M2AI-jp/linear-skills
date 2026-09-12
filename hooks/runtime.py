#!/usr/bin/env python3
"""Codex hook protocol adapter. No writes to Linear, no persisted permits."""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

import github_read
import linear_delete

from linear_read import (Unavailable, issue, project, project_issues, resource,
                         result_object, equivalent, state, complete_nodes)

ROOT = Path(__file__).resolve().parents[1]
MARK = "[linear-state-hook]"
WRITES = {"save_issue", "save_project", "save_milestone", "save_document",
          "save_issue_label", "create_issue_label",
          "delete_issue", "delete_project", "delete_document", "delete_milestone"}

def context(event, message):
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": MARK + " " + message}}

def deny(message):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
            "permissionDecision": "deny", "permissionDecisionReason": MARK + " " + message}}

def binding():
    values = []
    for name in ("AGENTS.md", "SSOT.md"):
        path = ROOT / name
        if path.exists():
            values.extend(re.findall(r"^Linear Project ID:[ \t]*(.*)$", path.read_text(), re.M))
    values = {value.strip().lower() for value in values}
    if len(values) != 1:
        raise Unavailable("AGENTS.md／SSOT.mdの現行Project入口が未指定または矛盾しています。")
    value = values.pop()
    if value == "未作成":
        return None
    if not re.fullmatch(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", value):
        raise Unavailable("現行Project IDが不正です。")
    return value

def tool_method(name):
    return name.removeprefix("mcp__linear__") if name.startswith("mcp__linear__") else ""

def start(event):
    current = binding()
    if not current:
        return context(event, "現行Projectは未作成。AGENTS.md／SSOT.mdの指定入口と原要求から新規Projectを構築し、入口を更新する。旧Projectを参照しない。")
    data = project(current)["project"]
    body = data.get("content") or data.get("description") or ""
    # This is current remote data, not evidence that the model understood it.
    return context(event, f"現行Projectを取得: {data['name']} {data['url']} "
                   f"状態={data['status']['name']} 更新={data['updatedAt']}\n"
                   + body + "\n担当Issue・依存先と正本を照合してから変更する。")

def shell_words(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars="();<>|&\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    segments = [[]]
    for token in lexer:
        if token in {";", "&&", "||", "|", "&", "\n"}:
            segments.append([])
        else:
            segments[-1].append(token)
    return [words for words in segments if words]


def gh_merge(words):
    if Path(words[0]).name != "gh":
        return False
    commands = []
    index = 1
    while index < len(words):
        word = words[index]
        if word in {"--repo", "-R"}:
            index += 2
            continue
        if word.startswith(("--repo=", "-R")):
            index += 1
            continue
        commands.append(word)
        index += 1
    return commands[:2] == ["pr", "merge"]


def merge_target(command):
    segments = shell_words(command)
    merges = [w for w in segments if gh_merge(w)]
    if not merges:
        return None
    words = merges[0]
    if os.environ.get("GH_HOST", "github.com") != "github.com":
        raise Unavailable("GitHub API読取と統合先ホストが一致しません。")
    if len(segments) != 1 or any(c in command for c in ("`", "$", ">", "<", "&", "|", ";", "\n")):
        raise Unavailable("統合は前提変更と分けた単独の同期コマンドで実行してください。")
    if len(words) not in {8, 9} or words[4] != "--repo" or words[6] != "--match-head-commit" \
            or (len(words) == 9 and words[8] not in {"--merge", "--squash", "--rebase"}):
        raise Unavailable("gh pr merge <PR> --repo <owner/repo> --match-head-commit <SHA>を使用してください。")
    return words[5], words[3], words[7]


def github_mutation(name, args):
    if "github" not in name.lower():
        return False
    operation = name.lower() + " " + str(args.get("method", "")).lower()
    return any(word in operation for word in ("merge_pull", "mergepull", "update_ref", "updateref",
               "create_ref", "delete_ref", "update_reference", "create_reference", "delete_reference", "push_files", "create_branch"))


def deletion_target(command, cwd=None):
    segments = shell_words(command)
    calls = [w for w in segments if Path(w[0]).name in {"python3", "python"}
             and any(Path(arg).name == "linear_delete.py" for arg in w[1:])]
    if not calls:
        return None
    words = calls[0]
    if len(segments) != 1 or len(words) != 3 or Path(words[0]).name != "python3" \
            or (Path(cwd or ROOT) / words[1]).resolve() != ROOT / "hooks/linear_delete.py" \
            or any(c in command for c in ("`", "$", ">", "<", "&", "|", ";", "\n")):
        raise Unavailable("削除は導入先のpython3 hooks/linear_delete.py <現在UUID>を単独実行してください。")
    return linear_delete.target_id(words[2], binding())


def shell_guard(command, cwd=None):
    segments = shell_words(command)
    deletion = deletion_target(command, cwd)
    if deletion:
        linear_delete.inspect(deletion, binding())
        return {}
    target_merge = merge_target(command)
    mutations = {"merge", "commit", "rebase", "cherry-pick", "reset", "push", "update-ref", "branch"}
    changes_context = any(Path(w[0]).name == "cd" or
        (Path(w[0]).name == "git" and set(w) & {"switch", "checkout"}) for w in segments)
    if len(segments) > 1 and changes_context and any(
            Path(w[0]).name == "git" and set(w) & mutations for w in segments):
        return deny("cd／switch／checkoutと更新を別操作に分け、対象を再確認してください。")
    if target_merge:
        github_read.validate_merge(*target_merge)
        return {}
    for words in segments:
        executable = Path(words[0]).name
        if executable == "linear-api" and words[1:] != ["--check"]:
            return deny("直接GraphQLの対象範囲を確認できません。現行Projectへ限定したLinear MCP操作を使ってください。")
        if executable == "curl" and any("api.linear.app" in word for word in words):
            return deny("直接のLinear API書込は未検証です。Linear MCP操作を使ってください。")
        if executable in {"gh", "curl"}:
            joined = " ".join(words)
            sensitive = re.search(r"/pulls/[^ /]+/merge|/git/(?:refs|matching-refs)|mergePullRequest|updateRef|createRef|deleteRef", joined)
            read_only = not any(w in joined for w in ("mutation", "--input", "--field", "--raw-field")) \
                and not any(w in words for w in ("-f", "-F", "-d", "--data", "--data-raw"))
            for flag in ("-X", "--method", "--request"):
                if flag in words:
                    read_only = read_only and words[words.index(flag) + 1].upper() in {"GET", "HEAD"}
            if re.search(r"(?:^|\s)(?:-X|--method=|--request=)(?!GET(?:\s|$)|HEAD(?:\s|$))\S+", joined):
                read_only = False
            if any(w.startswith(("--input=", "--field=", "--raw-field=", "--data=", "-f", "-F", "-d")) for w in words[1:]):
                read_only = False
            if sensitive and not read_only:
                return deny("直接GitHub merge／ref更新は未照合です。検証付きgh pr mergeを使用してください。")
        if executable != "git":
            continue
        for index, word in enumerate(words):
            force_target = None
            if ("checkout" in words and word == "-B") or ("switch" in words and word in {"-C", "--force-create"}):
                force_target = words[index + 1] if index + 1 < len(words) else ""
            elif "checkout" in words and word.startswith("-B"):
                force_target = word[2:]
            elif "switch" in words and word.startswith("--force-create="):
                force_target = word.split("=", 1)[1]
            elif "switch" in words and word.startswith("-C"):
                force_target = word[2:]
            if force_target in {"main", "master", "refs/heads/main", "refs/heads/master"}:
                return deny("main refを強制切替で更新できません。")
        writes = set(words) & mutations
        branch_change = "branch" in words and any(w.startswith(("-f", "-D", "-d", "-m", "-M", "--force", "--delete", "--move")) for w in words[1:])
        if "branch" in writes and not branch_change:
            writes.remove("branch")
        if not writes:
            continue
        if branch_change and any(re.search(r"(?:^|/)(main|master)$", w) for w in words):
            return deny("main refを直接変更できません。")
        if any(w.startswith(("--git-dir", "--work-tree")) for w in words):
            return deny("別Git領域への更新は対象を確認できません。")
        target = Path(cwd or ROOT)
        for index, word in enumerate(words[:-1]):
            if word == "-C":
                target = (target / words[index + 1]).resolve()
        try:
            result = subprocess.run(["git", "-C", str(target), "branch", "--show-current"],
                                    capture_output=True, text=True, check=False, timeout=10)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise Unavailable("Gitの現在ブランチを取得できません。") from error
        if result.returncode or not result.stdout.strip():
            raise Unavailable("Gitの更新先を確認できません。")
        protected = result.stdout.strip() in {"main", "master"}
        if set(words) & {"push", "update-ref"}:
            protected = protected or any(re.search(r"(?:^|[:/])(main|master)$", w) for w in words) \
                or bool(set(words) & {"--all", "--mirror", "--stdin"})
        if protected:
            return deny("mainへの直接書込です。作業ブランチで評価し、検証済み版の統合経路を使用してください。")
    return {}

def same_project(value, current):
    if value == current:
        return True
    if not value:
        return False
    data = project(current)["project"]
    return value in (data["name"], data["url"])

def scoped_issue(value, current):
    target = issue(value)
    if (target.get("project") or {}).get("id") != current:
        raise Unavailable("Issueの所属Projectが現行入口と一致しません。")
    return target

def scoped_resource(kind, value, current):
    target = resource(kind, value)
    owner = target.get("project") or (target.get("issue") or {}).get("project") or {}
    if owner.get("id") != current:
        raise Unavailable("参照先の所属Projectが現行入口と一致しません。")
    return target

def read_scope(method, args, current):
    if method == "get_project":
        return same_project(args.get("query"), current)
    if method == "get_milestone":
        if not same_project(args.get("project"), current):
            return False
        if re.fullmatch(r"[0-9a-fA-F-]{36}", args.get("query", "")):
            scoped_resource("projectMilestone", args["query"], current)
        return True
    if method in {"list_issues", "list_milestones"}:
        return same_project(args.get("project"), current)
    if method == "get_issue":
        scoped_issue(args.get("id"), current)
        return True
    if method == "get_document":
        scoped_resource("document", args.get("id"), current)
        return True
    if method == "list_documents":
        return same_project(args.get("projectId"), current)
    if method == "list_comments":
        if args.get("issueId"):
            scoped_issue(args["issueId"], current)
            return True
        for key, kind in (("documentId", "document"), ("milestoneId", "projectMilestone")):
            if args.get(key):
                scoped_resource(kind, args[key], current)
                return True
        return same_project(args.get("projectId"), current)
    return False

def entry_repair(name, args, cwd=None):
    # Codex's native apply_patch Hook input is tool_input.command.
    command = args.get("command")
    if name != "apply_patch" or not isinstance(command, str):
        return False
    lines = command.strip().splitlines()
    if not lines or lines[0] != "*** Begin Patch" or lines[-1] != "*** End Patch":
        return False
    paths = []
    for line in lines[1:-1]:
        match = re.fullmatch(r"\*\*\* (?:(?:Add|Update|Delete) File|Move to): (.+)", line)
        if match:
            paths.append((Path(cwd or ROOT) / match[1]).resolve())
        elif line.startswith("*** ") and line != "*** End of File":
            return False
    return bool(paths) and all(p in {ROOT / "AGENTS.md", ROOT / "SSOT.md",
        ROOT / ".codex/hooks.json", ROOT / ".codex/config.toml"}
        or p.is_relative_to(ROOT / "hooks") for p in paths)


def before(event):
    name = event.get("tool_name", "")
    args = event.get("tool_input") or {}
    method = tool_method(name)
    if name in {"apply_patch", "Edit", "Write"}:
        if entry_repair(name, args, event.get("cwd")):
            return {}
        current = binding()
        if current:
            project(current)
        return {}
    if name in {"Bash", "exec_command"}:
        return shell_guard(args.get("command", args.get("cmd", "")), args.get("workdir") or event.get("cwd"))
    if github_mutation(name, args):
        return deny("直接GitHub merge／ref更新は未照合です。検証付きgh pr mergeを使用してください。")
    if not method:
        return {}
    # Workspace metadata may be needed before a Project exists; it is not another Project's context.
    if method in {"list_teams", "get_team", "list_users", "get_user", "list_issue_statuses",
                  "get_issue_status", "list_issue_labels", "list_project_labels"}:
        return {}
    current = binding()
    if not current:
        if method == "save_project" and not args.get("id"):
            if args.get("state", "").lower() in {"completed", "done"}:
                return deny("未作成のProjectを完成済みとして作成しません。")
            return {}
        return deny("Project未作成です。旧対象を変更せず、新規作成してAGENTS.md／SSOT.mdの指定入口を接続してください。")
    if method not in WRITES:
        if read_scope(method, args, current):
            return {}
        return deny("対象Projectへ限定できない操作です。現行入口のIDを指定し、他Projectを探索・参照しないでください。")
    data = project(current)
    if method == "save_project":
        if not args.get("id"):
            return deny("現行Projectが存在します。重複作成せず、必要な再構成は現行対象へ行ってください。")
        if not same_project(args["id"], current):
            return deny("この開発環境の現行Project IDと変更先が一致しません。")
        if "state" in args and state(args["state"], data["projectStatuses"]["nodes"])["type"] == "completed":
            if any(k in args for k in ("description", "patch", "summary")):
                return deny("完成判定と同時に受入範囲を書き換えず、訂正を評価してから状態を更新してください。")
            rows = project_issues(current)
            required = [x for x in rows if not (x["state"]["type"] == "backlog"
                        and any(label["name"] == "Deferred" for label in complete_nodes(x["labels"])))]
            pending = [x["identifier"] for x in required
                       if x["state"]["type"] not in {"completed", "canceled", "duplicate"}]
            if pending:
                return deny("未完了の仕事があります: " + ", ".join(pending))
            blocked = [x["identifier"] + " ← " + r["issue"]["identifier"]
                       for x in required if x["state"]["type"] not in {"canceled", "duplicate"}
                       for r in complete_nodes(x["inverseRelations"])
                       if r["type"] == "blocks" and r["issue"]["state"]["type"] != "completed"]
            if blocked:
                return deny("必須成果が未完了の先行に依存しています: " + ", ".join(blocked))
            return context("PreToolUse", "機械的な未完了検査を通過。PMが原要求と接続した業務の実結果を評価する責任は残ります。全Issueの終了を全体受入の証明にしない。")
    elif method in {"save_issue_label", "create_issue_label"}:
        allowed = {"name", "teamId", "description", "color"}
        teams = {t["id"] for t in data["project"]["teams"]["nodes"]}
        if set(args) - allowed or args.get("name") != "Deferred" or args.get("teamId") not in teams:
            return deny("現行Projectの所属teamIdに厳密名Deferredを新規作成する操作だけを扱います。")
    elif method == "save_issue":
        target = scoped_issue(args["id"], current) if args.get("id") else None
        owner = current if target else args.get("project")
        if not same_project(owner, current) or ("project" in args and not same_project(args["project"], current)):
            return deny("Issueの所属Projectが現行入口と一致しません。")
        proposed_blockers = []
        for key in ("blockedBy", "blocks", "relatedTo", "removeBlockedBy", "removeBlocks", "removeRelatedTo"):
            for value in args.get(key, []):
                related = scoped_issue(value, current)
                if key == "blockedBy" and related["state"]["type"] != "completed":
                    proposed_blockers.append(related["identifier"])
        if args.get("parentId"):
            scoped_issue(args["parentId"], current)
        if args.get("milestone"):
            scoped_resource("projectMilestone", args["milestone"], current)
        if target and target["state"]["type"] == "completed" and set(args) & {"description", "patch"} \
                and "state" not in args:
            return deny("完了済み成果の本文を訂正する前に、影響する受入を再開してください。")
        if "state" in args:
            team_id = (target.get("team") or {}).get("id") if target else None
            if not target:
                teams = data["project"]["teams"]["nodes"]
                selected = [t for t in teams if args.get("team") in (t["id"], t["name"], t["key"])]
                if len(selected) != 1:
                    return deny("新規Issueのチームを現行Projectの実在チームへ一意に指定してください。")
                team_id = selected[0]["id"]
            next_type = state(args["state"], data["workflowStates"]["nodes"],
                              team_id)["type"]
            blockers = proposed_blockers + ([r["issue"]["identifier"] for r in target["inverseRelations"]["nodes"]
                if r["type"] == "blocks" and r["issue"]["state"]["type"] != "completed"] if target else [])
            reopening = target and target["state"]["type"] == "completed" and next_type != "completed"
            if next_type in {"started", "completed"} and blockers and not reopening:
                return deny("先行成果が未成立: " + ", ".join(blockers) + "。先行の訂正・調査は進められます。")
            if next_type == "completed":
                if not target or target["state"]["name"] != "In Review":
                    return deny("評価対象をIn Reviewへ置き、実結果を確認してからDoneへ遷移してください。")
                if set(args) & {"description", "patch", "title", "removeBlockedBy", "removeBlocks", "project", "team"}:
                    return deny("Doneと同時に受入対象や必須依存を変更しません。訂正・再評価を先に行ってください。")
                return context("PreToolUse", "対象・評価待ち状態・先行成果を確認。PMは対象版と原要求・実試験・外部観測を照合した範囲で完了を判断し、自己報告だけを証拠にしない。")
    elif method == "save_milestone":
        if args.get("project") != current:
            return deny("Milestoneの対象Projectが現行入口と一致しません。")
        if args.get("id"):
            scoped_resource("projectMilestone", args["id"], current)
    elif method == "save_document":
        if args.get("id"):
            scoped_resource("document", args["id"], current)
        elif not args.get("project") and not args.get("issue"):
            return deny("Documentの所属ProjectまたはIssueを指定してください。")
        if args.get("project") and not same_project(args["project"], current):
            return deny("Documentの移動先が現行Projectと一致しません。")
        if args.get("issue"):
            scoped_issue(args["issue"], current)
        if set(args) & {"team", "initiative", "cycle"}:
            return deny("Documentの対象がこのProjectの範囲外です。")
    else:
        # Document/delete coverage is deliberately not inferred from opaque IDs.
        return deny("この操作の対象照合は未実証です。削除・文書操作の検証を先に行ってください。")
    return {}

def after(event):
    if event.get("tool_name") in {"Bash", "exec_command"}:
        args = event.get("tool_input") or {}
        deletion = deletion_target(args.get("command", args.get("cmd", "")),
                                   args.get("workdir") or event.get("cwd"))
        if deletion:
            actual = linear_delete.inspect(deletion, binding())
            if not actual["trashed"]:
                raise Unavailable("Project削除後の読戻しが未反映です。再試行せず実状態を確認してください。")
            return context("PostToolUse", "指定Projectのtrashedを再取得。削除応答との整合を確認し、利用側の入口を訂正してください。")
        target = merge_target(args.get("command", args.get("cmd", "")))
        if target:
            merged, tip = github_read.verify_merge(*target)
            return context("PostToolUse", f"PR統合版={merged}、main={tip}をAPIで読み戻しました。意味の受入はPMが確認してください。")
    method = tool_method(event.get("tool_name", ""))
    if method not in WRITES:
        return {}
    args = event.get("tool_input") or {}
    result = result_object(event.get("tool_response"))
    if method in {"save_issue_label", "create_issue_label"}:
        return context("PostToolUse", "Deferred作成応答を受領。list_issue_labelsで所属teamIdと厳密名を読み戻し、再作成しないでください。")
    wrapper = {"save_issue": "issue", "save_project": "project",
               "save_milestone": "milestone", "save_document": "document"}.get(method)
    nested = result.get(wrapper)
    if not isinstance(nested, dict):
        nested = result
    target_id = nested.get("id") or args.get("id")
    if method == "save_issue" and target_id:
        actual = issue(target_id)
        for key in ("title", "description"):
            if key in args and not equivalent(actual.get(key), args[key]):
                raise Unavailable("Issueの" + key + "が要求と一致しません。部分反映として訂正してください。")
        if "state" in args and args["state"] not in (actual["state"]["id"], actual["state"]["name"]):
            raise Unavailable("Issue状態の読み戻しが一致しません。")
        return context("PostToolUse", f"{actual['identifier']}を再取得。状態={actual['state']['name']}。"
                       "保存確認は受入の意味の正しさを証明しません。")
    if method == "save_project" and target_id:
        data = project(target_id)
        actual = data["project"]
        if "description" in args and not equivalent(actual.get("content"), args["description"]):
            raise Unavailable("Project本文の読み戻しが一致しません。正規化差分を含め実データを確認してください。")
        if "state" in args and state(args["state"], data["projectStatuses"]["nodes"])["id"] != actual["status"]["id"]:
            raise Unavailable("Project状態の読み戻しが一致しません。部分反映として現在状態を訂正してください。")
        return context("PostToolUse", f"Projectを再取得: {actual['url']}。状態={actual['status']['name']}。"
                       "AGENTS.md／SSOT.mdの指定入口と今回の結果を一致させてください。")
    if method == "save_milestone" and target_id:
        actual = resource("projectMilestone", target_id)
        if any(k in args and not equivalent(actual.get(k), args[k]) for k in ("name", "description")):
            raise Unavailable("Milestoneの読み戻しが一致しません。")
        return {}
    if method == "save_document" and target_id:
        actual = resource("document", target_id)
        if any(k in args and not equivalent(actual.get(k), args[k]) for k in ("title", "content")):
            raise Unavailable("Documentの読み戻しが一致しません。")
        return {}
    raise Unavailable("変更後の対象を自動で読み戻せません。実データを確認し、未確認を明示してください。")

def changed_in_turn(event):
    """Use the native transcript, not an assistant-authored receipt."""
    path = event.get("transcript_path")
    if not path or not event.get("turn_id"):
        return False
    changed = False
    active = False
    try:
        with open(path) as stream:
            for line in stream:
                row = json.loads(line)
                payload = row.get("payload", {})
                if row.get("type") == "event_msg" and payload.get("type") == "task_started":
                    active = payload.get("turn_id") == event["turn_id"]
                if row.get("type") == "event_msg" and payload.get("type") == "item_completed" \
                        and payload.get("turn_id") == event["turn_id"]:
                    item = payload.get("item", {})
                    # This native error proves the MCP server was not called.
                    # Other failures may still have partially changed the service.
                    denied_before_execution = (item.get("error") or {}).get("message") == \
                        "MCP tool call requires approval, but approval policy is never"
                    if item.get("type") == "McpToolCall" and item.get("server") == "linear" \
                            and item.get("tool") in WRITES and not denied_before_execution:
                        changed = True
                if active and row.get("type") == "response_item":
                    method = tool_method(payload.get("name", ""))
                    if payload.get("name") == "apply_patch" or method in WRITES:
                        changed = True
    except (OSError, ValueError):
        return False
    return changed

def handle(event):
    kind = event.get("hook_event_name")
    if not Path(event.get("cwd", str(ROOT))).resolve().is_relative_to(ROOT):
        return {}
    if kind in {"SessionStart", "SubagentStart"}:
        return start(kind)
    if kind == "UserPromptSubmit":
        if str(event.get("prompt", "")).startswith(MARK):
            return {}
        return context(kind, "今回のユーザー指示を原要求と現行Projectへ照合する。読取依頼は読取で終える。"
                       "旧AI報告やHook生成文を要求・受入の証拠へ昇格させない。")
    if kind == "PreToolUse":
        return before(event)
    if kind == "PostToolUse":
        return after(event)
    if kind in {"Stop", "SubagentStop"}:
        if event.get("stop_hook_active") or not changed_in_turn(event):
            return {}
        return {"decision": "block", "reason": MARK + " 今回の変更を原要求と実結果へ照合し、"
                "必要な正本・Linearの訂正と読み戻しを一度行う。既に反映済みなら繰り返さない。"
                "未達を含め元の依頼へ回答する。この指示を要求や合格証拠に保存しない。"}
    return {}

def main():
    kind = ""
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError("invalid event")
        kind = event.get("hook_event_name", "")
        if kind in {"PreToolUse", "PostToolUse"} and not isinstance(event.get("tool_input", {}), dict):
            raise ValueError("tool_input must be an object")
        result = handle(event)
    except (Unavailable, OSError, ValueError, KeyError, TypeError) as exc:
        message = str(exc) if isinstance(exc, Unavailable) else "Hookの入力・設定・取得結果を確認できません。"
        if not kind:
            print(MARK + " " + message, file=sys.stderr)
            return 2
        if kind == "PreToolUse":
            result = deny(message)
        elif kind in {"SessionStart", "SubagentStart"}:
            result = context(kind, message + " 正本を再取得し、確認まで依存する変更を行わない。")
        else:
            result = {"systemMessage": MARK + " " + message}
    print(json.dumps(result, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
