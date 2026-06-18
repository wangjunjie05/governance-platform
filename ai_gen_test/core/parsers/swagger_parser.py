import json
from typing import Any, Dict, List, Tuple

try:
    import yaml
except ImportError:
    yaml = None

from core.config import BASE_URL


def load_swagger(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if path.lower().endswith(".json"):
        return json.loads(text)
    if path.lower().endswith((".yml", ".yaml")):
        if yaml is None:
            raise RuntimeError("未安装 pyyaml，请先执行: pip install pyyaml")
        return yaml.safe_load(text)
    try:
        return json.loads(text)
    except Exception:
        if yaml is None:
            raise RuntimeError("文件不是 json，且未安装 pyyaml，无法解析 yaml")
        return yaml.safe_load(text)


def resolve_ref(spec: Dict[str, Any], obj: Any) -> Any:
    if not isinstance(obj, dict):
        return obj
    ref = obj.get("$ref")
    if not ref or not ref.startswith("#/"):
        return obj
    cur: Any = spec
    for p in ref.lstrip("#/").split("/"):
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return obj
    return cur


def extract_endpoints(spec: Dict[str, Any]) -> List[Tuple[str, str, Dict[str, Any]]]:
    endpoints = []
    for path, item in (spec.get("paths", {}) or {}).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            method_lower = str(method).lower()
            if method_lower in {"get", "post", "put", "delete", "patch", "head", "options"} and isinstance(op, dict):
                endpoints.append((path, method_lower.upper(), op))
    return endpoints


def build_api_doc(spec: Dict[str, Any], path: str, method: str, op: Dict[str, Any]) -> str:
    title = op.get("summary") or op.get("operationId") or f"{method} {path}"
    params = op.get("parameters") or []
    responses = op.get("responses") or {}

    lines = [f"接口名称：{title}", f"请求方式：{method} {path}"]
    if params:
        lines.append("请求参数：")
        for p in params:
            if not isinstance(p, dict):
                continue
            name = p.get("name", "")
            where = p.get("in", "")
            required = p.get("required", False)
            ptype = p.get("type", "")
            if "schema" in p:
                schema = resolve_ref(spec, p.get("schema"))
                ptype = schema.get("type", "object") if isinstance(schema, dict) else "object"
                lines.append(
                    f"- {name} ({where}) required={required} type={ptype} "
                    f"schema={json.dumps(schema, ensure_ascii=False)[:1200]}"
                )
            else:
                lines.append(f"- {name} ({where}) required={required} type={ptype}")

    if responses:
        lines.append("Swagger 声明的返回码：")
        for code, resp in responses.items():
            desc = resp.get("description", "") if isinstance(resp, dict) else ""
            lines.append(f"- {code}: {desc}")
    lines.append(f"测试环境 BASE_URL：{BASE_URL}")
    return "\n".join(lines)
