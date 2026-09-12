"""Read the existing Linear API; never write or keep a second state store."""
import json
import html
import re
import subprocess
from urllib.parse import unquote

class Unavailable(Exception):
    pass

def query(document, variables=None):
    try:
        result = subprocess.run(
            ["linear-api"], input=json.dumps({"query": document, "variables": variables or {}}),
            capture_output=True, text=True, timeout=12, check=False)
        if result.returncode:
            raise Unavailable("Linear APIの取得に失敗。変更は再試行せず正本を再取得してください。")
        payload = json.loads(result.stdout)
        if payload.get("errors") or not isinstance(payload.get("data"), dict):
            raise Unavailable("Linear APIの結果が不完全です。")
        return payload["data"]
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise Unavailable("Linear APIを確認できません。未確認を成功として扱いません。") from None

def project(project_id):
    data = query("""query($id: String!) {
      project(id: $id) {
        id name url description content updatedAt archivedAt trashed
        status { id name type }
        teams(first: 20) {
          nodes { id name key states(first: 30) { nodes { id name type } pageInfo { hasNextPage } } }
          pageInfo { hasNextPage }
        }
      }
      projectStatuses { nodes { id name type } }
    }""", {"id": project_id})
    value = data.get("project")
    if not value or value.get("trashed") or value.get("archivedAt"):
        raise Unavailable("現行Projectが存在しないか削除・アーカイブされています。入口を訂正してください。")
    teams = complete_nodes(value["teams"])
    data["workflowStates"] = {"nodes": [dict(s, teamId=t["id"])
        for t in teams for s in complete_nodes(t["states"])]}
    return data

def complete_nodes(connection):
    if not isinstance(connection, dict) or not isinstance(connection.get("nodes"), list) \
            or not isinstance(connection.get("pageInfo"), dict) \
            or connection["pageInfo"].get("hasNextPage") is not False:
        raise Unavailable("取得が一部にとどまっています。残りを確認するまで依存する変更は行えません。")
    return connection["nodes"]

def issue(issue_id):
    data = query("""query($id: String!) {
      issue(id: $id) {
        id identifier title description updatedAt archivedAt trashed
        state { id name type } project { id } team { id }
        inverseRelations(first: 100) {
          nodes { type issue { id identifier state { type } } }
          pageInfo { hasNextPage }
        }
      }
    }""", {"id": issue_id})
    value = data.get("issue")
    if not value or value.get("trashed") or value.get("archivedAt"):
        raise Unavailable("Issueの現行状態を取得できません。")
    complete_nodes(value["inverseRelations"])
    return value

def resource(kind, value):
    fields = {
        "projectMilestone": "id name description project { id }",
        "document": "id title content project { id } issue { id project { id } }",
    }
    if kind not in fields:
        raise Unavailable("対象の種別を解決できません。")
    data = query("query($id: String!) { " + kind + "(id: $id) { " + fields[kind] + " } }",
                 {"id": value}).get(kind)
    if not data:
        raise Unavailable("対象を取得できません。")
    return data

def project_issues(project_id):
    rows, after, seen = [], None, set()
    while True:
        data = query("""query($id: String!, $after: String) {
      project(id: $id) { issues(first: 20, after: $after) {
        nodes {
          identifier state { type }
          labels(first: 50) { nodes { name } pageInfo { hasNextPage } }
          inverseRelations(first: 50) {
            nodes { type issue { identifier state { type } } }
            pageInfo { hasNextPage }
          }
        } pageInfo { hasNextPage endCursor }
      } }
    }""", {"id": project_id, "after": after})
        if not data.get("project"):
            raise Unavailable("Projectを取得できません。")
        connection = data["project"]["issues"]
        page = connection.get("pageInfo")
        if not isinstance(page, dict) or type(page.get("hasNextPage")) is not bool \
                or not isinstance(connection.get("nodes"), list):
            raise Unavailable("Project Issueの取得が不完全です。")
        for row in connection["nodes"]:
            try:
                if not row["identifier"] or not row["state"]["type"]:
                    raise ValueError()
                for label in complete_nodes(row.get("labels")):
                    if not isinstance(label["name"], str):
                        raise ValueError()
                for relation in complete_nodes(row.get("inverseRelations")):
                    if not relation["type"] or not relation["issue"]["identifier"] \
                            or not relation["issue"]["state"]["type"]:
                        raise ValueError()
            except (KeyError, TypeError, ValueError):
                raise Unavailable("Issueの状態・ラベル・依存の取得が不完全です。") from None
        rows.extend(connection["nodes"])
        if not page["hasNextPage"]:
            return rows
        after = connection["pageInfo"]["endCursor"]
        if not after or after in seen:
            raise Unavailable("次ページを取得できません。")
        seen.add(after)

def state(value, states, team_id=None):
    candidates = [s for s in states if not team_id or s.get("teamId") == team_id]
    found = [s for s in candidates if value in (s["id"], s["name"])]
    if len(found) != 1:
        raise Unavailable("状態名またはIDを一意に解決できません。状態カテゴリから個別状態を推定しません。")
    return found[0]

def state_type(value, states):
    return state(value, states)["type"]

def normalized(text):
    """Ignore only known Linear rendering changes; preserve link destinations."""
    value = html.unescape(text or "")
    value = re.sub(r'<issue\b[^>]*href="([^"]+)"[^>]*>([^<]+)</issue>',
                   lambda m: '[' + m[2] + '](' + m[1] + ')', value)
    value = re.sub(r'\]\(<([^>]+)>\)', r'](\1)', value)
    def link(match):
        label, url = match[1], canonical_url(match[2])
        return url if label == url else '[' + label + '](' + url + ')'
    value = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link, value)
    value = re.sub(r'^\s*[*-] ', '- ', value, flags=re.M)
    return '\n'.join(line.strip() for line in value.splitlines()
                     if line.strip() and not re.fullmatch(r'[ |:\-]+', line))

def canonical_url(url):
    def decode(match):
        try:
            value = unquote(match[0], errors="strict")
        except UnicodeError:
            return match[0].upper()
        return ''.join(c if ord(c) > 127 or c.isalnum() or c in '-._~'
                       else '%' + format(ord(c), '02X') for c in value)
    return re.sub(r'(?:%[0-9a-fA-F]{2})+', decode, url)

def equivalent(actual, expected):
    value, wanted = normalized(actual), normalized(expected)
    def added_link(match):
        label, url = match[1], match[2]
        if ('[' + label + '](') not in wanted and re.fullmatch(r'[A-Z]+-\d+', label) \
                and re.match(r'https://linear\.app/[^/]+/issue/' + re.escape(label) + r'(?:/|$)', url):
            return label
        return match[0]
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', added_link, value) == wanted

def result_object(response):
    if not isinstance(response, dict) or response.get("isError"):
        raise Unavailable("操作結果が失敗または不明です。部分反映を確認し、書込を繰り返さないでください。")
    if isinstance(response.get("structuredContent"), dict):
        return response["structuredContent"]
    if "content" in response:
        for item in response["content"]:
            if item.get("type") == "text":
                try:
                    value = json.loads(item["text"])
                    if isinstance(value, dict):
                        return value
                except ValueError:
                    continue
        raise Unavailable("操作結果から対象を特定できません。")
    return response
