"""Read GitHub native protection and results through the existing gh identity."""
import json
import re
import subprocess

from linear_read import Unavailable


def api(path):
    try:
        result = subprocess.run(
            ["gh", "api", "--hostname", "github.com", "--method", "GET", path],
            capture_output=True, text=True, timeout=20, check=False)
        if result.returncode:
            raise Unavailable("GitHub API取得失敗。統合は未確認です。")
        return json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        raise Unavailable("GitHub API応答を確認できません。") from error


def require(condition, message):
    if not condition:
        raise Unavailable(message)


def pull(repo, number, sha):
    require(bool(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo))
            and str(number).isdigit() and int(number) > 0
            and bool(re.fullmatch(r"[0-9a-f]{40}", sha)), "統合対象の形式が不正です。")
    data = api(f"repos/{repo}/pulls/{number}")
    require(data["head"]["sha"] == sha and data["base"]["ref"] == "main"
            and data["base"]["repo"]["full_name"].lower() == repo.lower(),
            "PRのhead／base／repoが指定と一致しません。")
    return data


def validate_merge(repo, number, sha):
    pr = pull(repo, number, sha)
    require(pr["state"] == "open" and not pr["draft"]
            and pr.get("mergeable") is True and pr.get("mergeable_state") == "clean",
            "PRが同期統合可能な状態ではありません。")
    prefix = f"repos/{repo}"
    base = api(prefix + "/branches/main")["commit"]["sha"]
    require(pr["base"]["sha"] == base, "PRのbaseが現在mainと一致しません。")
    rules = api(prefix + "/rules/branches/main")
    require(isinstance(rules, list) and not any(r.get("type") == "merge_queue" for r in rules),
            "同期統合できないmerge queueまたは未確認のルールです。")
    protection = api(prefix + "/branches/main/protection")
    required = protection.get("required_status_checks") or {}
    require(required.get("strict") is True
            and (protection.get("enforce_admins") or {}).get("enabled") is True,
            "strict保護と管理者適用を確認できません。")
    checks = required.get("checks") or []
    require(bool(checks) and all(isinstance(c.get("app_id"), int) and c["app_id"] > 0
                               for c in checks)
            and set(required.get("contexts") or []).issubset({c["context"] for c in checks}),
            "必要チェックの発行元を一意に確認できません。")
    # This route supports checks on an up-to-date head; merge-only suites fail closed.
    comparison = api(prefix + f"/compare/{base}...{sha}")
    require(comparison["status"] in {"ahead", "identical"}, "headに現在mainが含まれていません。")
    runs = []
    for page in range(1, 101):
        response = api(prefix + f"/commits/{sha}/check-runs?filter=all&per_page=100&page={page}")
        batch = response["check_runs"]
        runs.extend(batch)
        if len(runs) >= response["total_count"]:
            break
        require(bool(batch), "チェック一覧が部分応答です。")
    else:
        raise Unavailable("チェック一覧を全件確認できません。")
    for check in checks:
        candidates = [r for r in runs if r["name"] == check["context"]
                      and (r.get("app") or {}).get("id") == check["app_id"]]
        require(bool(candidates), "必要チェックの指定発行元の結果がありません。")
        latest = max(candidates, key=lambda r: r["id"])
        require(latest["head_sha"] == sha and latest["status"] == "completed"
                and latest["conclusion"] == "success", "必要チェックの最新版が成功していません。")
    require(pull(repo, number, sha)["base"]["sha"] == base
            and api(prefix + "/branches/main")["commit"]["sha"] == base,
            "検査中にhead／baseが移動しました。再評価してください。")


def verify_merge(repo, number, sha):
    pr = pull(repo, number, sha)
    merged = pr.get("merge_commit_sha") or ""
    require(pr.get("merged") is True and bool(re.fullmatch(r"[0-9a-f]{40}", merged)),
            "PRの統合を読み戻せません。再実行せず実状態を確認してください。")
    tip = api(f"repos/{repo}/branches/main")["commit"]["sha"]
    relation = api(f"repos/{repo}/compare/{merged}...{tip}")
    require(relation["status"] in {"ahead", "identical"}, "統合版とmainの対応が確認できません。")
    return merged, tip
