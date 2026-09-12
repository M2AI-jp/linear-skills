"""Delete only the Project bound by the deployment's native entry, then read it back."""
import json
import re
import subprocess
import sys

from linear_read import Unavailable, query


def target_id(value, current):
    if not isinstance(value, str) or not re.fullmatch(
            r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", value) or value != current:
        raise Unavailable("削除UUIDが現在Projectの一意な入口と一致しません。")
    return value


def snapshot(project_id):
    value = query("query($id: String!) { project(id: $id) { id name trashed archivedAt } }",
                  {"id": project_id}).get("project")
    if (not isinstance(value, dict) or value.get("id") != project_id or "trashed" not in value
            or (value["trashed"] is not None and not isinstance(value["trashed"], bool))):
        raise Unavailable("指定Projectの実在・削除状態を確認できません。不存在や取得失敗を削除成功にしません。")
    return value


def inspect(project_id, current):
    return snapshot(target_id(project_id, current))


def delete_project(project_id, binding):
    before = inspect(project_id, binding())
    if before["trashed"] is True:
        return {"id": project_id, "result": "already_deleted", "trashed": True}
    # Recheck the native entry immediately before the sole mutation.
    target_id(project_id, binding())
    confirmed = False
    try:
        response = subprocess.run(["linear-api"], input=json.dumps({
            "query": "mutation($id: String!) { projectDelete(id: $id) { success } }",
            "variables": {"id": project_id}}), capture_output=True, text=True, timeout=12, check=False)
        payload = json.loads(response.stdout)
        confirmed = response.returncode == 0 and not payload.get("errors") and \
            ((payload.get("data") or {}).get("projectDelete") or {}).get("success") is True
    except (OSError, ValueError, AttributeError, subprocess.TimeoutExpired):
        pass
    # Even an ambiguous mutation response can have applied. Never retry it here.
    after = snapshot(project_id)
    if not confirmed or after["trashed"] is not True:
        raise Unavailable(f"削除応答または読戻しが不一致。id={project_id} trashed={after['trashed']}。部分失敗として実状態を確認し、書込を反復しないでください。")
    return {"id": project_id, "result": "deleted", "trashed": True}


def main(argv=None):
    from runtime import binding
    arguments = sys.argv[1:] if argv is None else argv
    try:
        if len(arguments) != 1:
            raise Unavailable("使い方: python3 hooks/linear_delete.py <現在Project UUID>")
        print(json.dumps(delete_project(arguments[0], binding), ensure_ascii=False))
        return 0
    except (Unavailable, OSError, ValueError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
