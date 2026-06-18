import json
import re
from typing import Any, Dict, List

from core.utils.common import safe_name
from core.config import BASE_URL


def render_value(v: Any) -> str:
    """把 Python 值安全渲染到生成的测试脚本中。

    之前这里用 json.dumps，会把 None/True/False 渲染成 null/true/false，
    这些不是合法的 Python 字面量，异常用例里一旦出现 null 就会导致 pytest 收集失败。
    """
    return repr(v)


def parse_json_like(value: Any) -> Any:
    """日志中的 request_body/response_body 可能是 dict，也可能是 JSON 字符串。"""
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except Exception:
            return value
    return value




def replay_headers(headers: Any) -> Dict[str, Any]:
    """从代理日志里提取适合回放的请求头。

    只保留和接口鉴权/内容类型相关的头，避免 Host、Content-Length、压缩等运行环境相关字段影响请求。
    真实项目可能依赖 Cookie/JSESSIONID 或 Authorization，所以这里会保留常见认证头。
    """
    if not isinstance(headers, dict):
        return {}
    allow = {"cookie", "authorization", "x-token", "token", "access_token", "content-type", "accept", "istoken", "repeatsubmit"}
    result: Dict[str, Any] = {}
    for key, value in headers.items():
        low = str(key).lower()
        if low in allow and value not in (None, "", "***"):
            result[str(key)] = value
    return result



def default_replay_headers(code_info: Dict[str, Any]) -> Dict[str, Any]:
    return replay_headers((code_info or {}).get("default_headers") or {})


def merge_with_latest_auth(headers: Dict[str, Any], default_headers: Dict[str, Any]) -> Dict[str, Any]:
    """合并日志中最新认证头。

    JSESSIONID 认证项目优先使用 Cookie，避免旧 Authorization/token 干扰。
    无 Cookie 时继续兼容 Authorization。函数名保持不变是为了兼容已有调用。
    """
    result = dict(headers or {})
    latest_cookie = None
    latest_auth = None
    for key, value in (default_headers or {}).items():
        low = str(key).lower()
        if low == "cookie" and value and "jsessionid=" in str(value).lower():
            latest_cookie = value
        elif low == "authorization" and value:
            latest_auth = value

    if latest_cookie:
        result = {
            k: v
            for k, v in result.items()
            if str(k).lower() not in {"cookie", "authorization", "x-token", "token", "access_token"}
        }
        result["Cookie"] = latest_cookie
    elif latest_auth:
        result = {k: v for k, v in result.items() if str(k).lower() != "authorization"}
        result["Authorization"] = latest_auth
    return result


def needs_unique_body(method: str, path: str) -> bool:
    if (method or "").upper() != "POST":
        return False
    text = (path or "").lower()
    if any(x in text for x in ["/login", "/logout", "/cancel", "/authrole"]):
        return False
    return True


def normalize_params(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: Dict[str, Any] = {}
    for k, v in value.items():
        if isinstance(v, list) and len(v) == 1:
            result[k] = v[0]
        else:
            result[k] = v
    return result


def build_url_expr(path: str, path_params: Dict[str, Any]) -> str:
    url_path = path
    for k, v in path_params.items():
        url_path = url_path.replace("{" + str(k) + "}", str(v))
    return f'f"{{BASE_URL}}{url_path}"'


def _safe_response_assertions(lines: List[str], response_body: Any, business_code: Any) -> None:
    """只生成确定性强的断言，避免 AI 幻觉字段。

    导出类接口通常返回 Excel/ZIP/PDF，不能调用 response.json()。
    如果代理日志标记了 _body_omitted，说明响应体是二进制或过长内容，此时只断言状态码。
    """
    response_body = parse_json_like(response_body)
    if isinstance(response_body, dict) and response_body.get("_body_omitted"):
        return

    if business_code is not None:
        lines.append("    data = response.json()")
        lines.append("    assert isinstance(data, dict)")
        lines.append(f"    assert data.get('code') == {render_value(business_code)}")
        return

    if isinstance(response_body, dict):
        if "code" in response_body:
            lines.append("    data = response.json()")
            lines.append("    assert isinstance(data, dict)")
            lines.append(f"    assert data.get('code') == {render_value(response_body.get('code'))}")
        elif "detail" in response_body:
            lines.append("    data = response.json()")
            lines.append("    assert isinstance(data, dict)")
            lines.append(f"    assert data.get('detail') == {render_value(response_body.get('detail'))}")

def generate_fallback_code(method: str, path: str, log_cases: List[Dict[str, Any]], code_info: Dict[str, Any]) -> str:
    """
    确定性模板生成器。
    - 有日志：使用日志中的真实 path/body/query/status/business_code 生成脚本。
    - 无日志：根据代码扫描结果做保守兜底，只保证代码结构正确。
    """
    lines = [
        "import os",
        "import requests",
    ]
    if needs_unique_body(method, path):
        lines.extend([
            "from api_test_utils import make_unique_body",
        ])
    lines.extend([
        "",
        f'BASE_URL = os.getenv("BASE_URL", "{BASE_URL}")',
        "",
    ])
    method_lower = method.lower()

    if not log_cases:
        status = 200
        if code_info.get("status_codes"):
            status = 200 if 200 in code_info.get("status_codes", []) else code_info["status_codes"][0]
        body = {}
        path_params = {}
        for name in re.findall(r"\{([^}]+)\}", path):
            path_params[name] = 1
        log_cases = [
            {
                "path_params": path_params,
                "query_params": {},
                "body": body,
                "http_status": status,
                "business_code": 200 if status == 200 else None,
                "response_body": {},
                "headers": default_replay_headers(code_info),
            }
        ]

    for idx, case in enumerate(log_cases, 1):
        status = case.get("http_status") or 200
        business_code = case.get("business_code")
        path_params = case.get("path_params") or {}
        query_params = normalize_params(case.get("query_params") or {})
        body = parse_json_like(case.get("body") or {})
        headers = merge_with_latest_auth(replay_headers(case.get("headers") or case.get("request_headers") or {}), default_replay_headers(code_info)) or default_replay_headers(code_info)
        response_body = case.get("response_body")
        actual_path = case.get("path")

        if actual_path:
            url_expr = f'f"{{BASE_URL}}{actual_path}"'
        else:
            url_expr = build_url_expr(path, path_params)

        func_name = f"test_{safe_name(method)}_{safe_name(path)}_case_{idx}"
        lines.append(f"def {func_name}():")
        lines.append(f"    url = {url_expr}")
        if headers:
            lines.append(f"    headers = {render_value(headers)}")
        else:
            lines.append("    headers = {}")
        if method.upper() in {"GET", "DELETE"}:
            if query_params:
                lines.append(f"    params = {render_value(query_params)}")
                lines.append(f"    response = requests.{method_lower}(url, params=params, headers=headers or None, timeout=10)")
            else:
                lines.append(f"    response = requests.{method_lower}(url, headers=headers or None, timeout=10)")
        else:
            lines.append(f"    payload = {render_value(body)}")
            if needs_unique_body(method, path):
                lines.append("    payload = make_unique_body(payload)")
            lines.append(f"    response = requests.{method_lower}(url, json=payload, headers=headers or None, timeout=10)")
        lines.append(f"    assert response.status_code == {int(status)}")
        _safe_response_assertions(lines, response_body, business_code)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
