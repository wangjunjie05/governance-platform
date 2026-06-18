import copy
import json
import re
from typing import Any, Dict, List, Tuple

from core.utils.common import safe_name
from core.config import BASE_URL, MAX_NORMAL_CASES_PER_API
from core.generators.fallback_generator import parse_json_like, normalize_params, render_value, replay_headers


_INVALID_PATH_VALUES = {"", "none", "null", "undefined", "nan"}


def _looks_invalid_path_value(value: Any) -> bool:
    text = str(value).strip()
    return text.lower() in _INVALID_PATH_VALUES


def _exception_branch_values(code_info: Dict[str, Any]) -> set:
    """从代码条件里提取明显代表异常分支的常量值。

    例如 "PAID".equals(orderId)、"FINISHED".equals(orderId)。
    这些值通常用于构造异常用例，不适合作为正常基线数据。
    """
    values = set()
    for hint in code_info.get("enum_or_constant_hints", []) or []:
        for m in re.finditer(r'"([^"]+)"', str(hint)):
            values.add(m.group(1))
        for m in re.finditer(r"'([^']+)'", str(hint)):
            values.add(m.group(1))
    return values


def _is_good_success_case(case: Dict[str, Any], code_info: Dict[str, Any]) -> bool:
    try:
        if int(case.get("http_status") or 0) >= 400:
            return False
    except Exception:
        return False

    bad_values = _exception_branch_values(code_info)
    path_params = case.get("path_params") or {}
    for value in path_params.values():
        if _looks_invalid_path_value(value):
            return False
        if str(value) in bad_values:
            return False

    path = str(case.get("path") or "")
    for part in path.strip("/").split("/"):
        if _looks_invalid_path_value(part):
            return False
        if part in bad_values:
            return False
    return True


def _choose_success_case(log_cases: List[Dict[str, Any]], code_info: Dict[str, Any]) -> Dict[str, Any]:
    for case in log_cases or []:
        if _is_good_success_case(case, code_info):
            return case
    # 不能把 /None/cancel、/null 等脏成功日志当正常基线。
    # 如果没有高质量成功样本，交给代码推断生成一条更合理的正常用例。
    return {}


def _valid_path_value(field: str, path: str, code_info: Dict[str, Any]) -> Any:
    name = (field or "").lower()
    # 路径参数没有 DTO 校验时，不能用 None/1 这种随意值。
    # 按常见命名生成一个更像真实业务数据的默认值。
    if "order" in name:
        return "ORD202606050001"
    if "user" in name:
        return 1
    if "product" in name:
        return 1
    if name == "id" or name.endswith("id"):
        # 如果路径里明显是订单接口，id 也使用订单号。
        if "orders" in (path or "").lower():
            return "ORD202606050001"
        return 1
    return "demo"


def _valid_value(java_type: str) -> Any:
    t = (java_type or "").lower()
    if any(x in t for x in ["integer", "int", "long"]):
        return 1
    if any(x in t for x in ["bigdecimal", "double", "float"]):
        return 1
    if "boolean" in t:
        return True
    return "demo"



def _default_headers(code_info: Dict[str, Any]) -> Dict[str, Any]:
    headers = (code_info or {}).get("default_headers") or {}
    return replay_headers(headers)


def _needs_unique_body(method: str, path: str) -> bool:
    """判断正常用例是否需要对请求体做唯一化处理。

    对新增类接口，直接回放日志里的用户、角色、配置等数据容易因为“已存在”失败。
    这里只对明显的新增 POST 接口做处理；登录、取消、查询类接口不处理。
    """
    if (method or "").upper() != "POST":
        return False
    text = (path or "").lower()
    if any(x in text for x in ["/login", "/logout", "/cancel", "/authrole"]):
        return False
    return True



def _build_base_request(path: str, log_cases: List[Dict[str, Any]], code_info: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any], str]:
    # 优先使用真实成功日志作为基础数据，这样异常用例只改一个字段，稳定性最高。
    # 但要排除 /None/cancel、异常分支常量等不合理成功样本，避免把脏日志当正常基线。
    success_case = _choose_success_case(log_cases, code_info)
    if success_case:
        body = parse_json_like(success_case.get("body") or {})
        return (
            dict(success_case.get("path_params") or {}),
            normalize_params(success_case.get("query_params") or {}),
            body if isinstance(body, dict) else {},
            replay_headers(success_case.get("headers") or success_case.get("request_headers") or {}) or _default_headers(code_info),
            str(success_case.get("path") or ""),
        )

    for case in log_cases or []:
        body = parse_json_like(case.get("body") or {})
        return (
            dict(case.get("path_params") or {}),
            normalize_params(case.get("query_params") or {}),
            body if isinstance(body, dict) else {},
            replay_headers(case.get("headers") or case.get("request_headers") or {}) or _default_headers(code_info),
            str(case.get("path") or ""),
        )

    path_params: Dict[str, Any] = {name: _valid_path_value(name, path, code_info) for name in re.findall(r"\{([^}]+)\}", path)}
    query_params: Dict[str, Any] = {}
    body: Dict[str, Any] = {}

    for rule in code_info.get("validation_rules", []) or []:
        field = rule.get("field")
        if not field:
            continue
        location = rule.get("location", "body")
        value = rule.get("example") if rule.get("example") not in (None, "") else _valid_value(rule.get("type", ""))
        if location == "path":
            path_params[field] = value
        elif location == "query":
            query_params[field] = value
        else:
            body[field] = value
    return path_params, query_params, body, _default_headers(code_info), ""


def _apply_case(base_path: Dict[str, Any], base_query: Dict[str, Any], base_body: Dict[str, Any], case: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    path_params = copy.deepcopy(base_path)
    query_params = copy.deepcopy(base_query)
    body = copy.deepcopy(base_body)

    field = case.get("field")
    if not field:
        return path_params, query_params, body

    location = case.get("location", "body")
    value = case.get("value")
    remove = case.get("case_type") == "missing_param" or value == "<remove this field>"

    target = body
    if location == "query":
        target = query_params
    elif location == "path":
        target = path_params
        remove = False  # path 参数不能真正删除，只能改成非法值。
        if value == "<remove this field>":
            value = ""

    if remove:
        target.pop(field, None)
    else:
        target[field] = value
    return path_params, query_params, body


def _url_expr(path: str, path_params: Dict[str, Any], actual_path: str = "") -> str:
    if actual_path:
        url_path = actual_path
    else:
        url_path = path
        for k, v in path_params.items():
            url_path = url_path.replace("{" + str(k) + "}", str(v))
    return f'f"{{BASE_URL}}{url_path}"'


def _is_executable_case(case: Dict[str, Any]) -> bool:
    # 业务分支/代码条件只有提示价值，不一定能直接构造稳定请求；先交给 AI，不用模板强制执行。
    return bool(case.get("field")) and case.get("location") in {"body", "query", "path"}


def build_exception_test_code(method: str, path: str, log_cases: List[Dict[str, Any]], code_info: Dict[str, Any], exception_cases: List[Dict[str, Any]]) -> str:
    executable_cases = [case for case in (exception_cases or []) if _is_executable_case(case)]
    if not executable_cases:
        return ""

    base_path, base_query, base_body, base_headers, actual_path = _build_base_request(path, log_cases, code_info)
    rows = []
    for idx, case in enumerate(executable_cases, 1):
        path_params, query_params, body = _apply_case(base_path, base_query, base_body, case)
        # 如果异常用例修改的是 path 参数，不能再使用真实日志里的 actual_path，
        # 否则会把 /users/{id} 中的 abc 又覆盖回 /users/1，导致异常用例实际走成正常接口。
        case_actual_path = "" if case.get("location") == "path" else actual_path
        rows.append({
            "id": f"ex_{idx}_{safe_name(case.get('case_type', 'exception'))}_{safe_name(case.get('field', 'case'))}",
            "description": case.get("description", ""),
            "exception_type": case.get("case_type", ""),
            "path_params": path_params,
            "query_params": query_params,
            "body": body,
            "headers": base_headers,
            "expected_status": int(case.get("expected_http_status") or 400),
            "actual_path": case_actual_path,
        })

    method_lower = method.lower()
    lines = [
        "",
        "# 以下异常用例由程序根据 DTO 校验注解和接口参数规则自动扩展。",
        "AUTO_EXCEPTION_CASES = " + render_value(rows),
        "",
        "@pytest.mark.parametrize(\"case\", AUTO_EXCEPTION_CASES, ids=[c['id'] for c in AUTO_EXCEPTION_CASES])",
        f"def test_auto_exception_{safe_name(method)}_{safe_name(path)}(case):",
    ]
    # 构造 URL。每条用例的 path_params 可能不同，不能直接用 f-string 嵌套替换，使用普通 replace 更直观。
    lines.append(f"    url_path = {render_value(path)}")
    lines.append("    for key, value in case.get('path_params', {}).items():")
    lines.append("        url_path = url_path.replace('{' + str(key) + '}', str(value))")
    lines.append("    if case.get('actual_path'):")
    lines.append("        url_path = case.get('actual_path')")
    lines.append("    url = f'{BASE_URL}{url_path}'")
    if method.upper() in {"GET", "DELETE"}:
        lines.append(f"    response = requests.{method_lower}(url, params=case.get('query_params') or None, headers=case.get('headers') or None, timeout=10)")
    else:
        lines.append(f"    response = requests.{method_lower}(url, params=case.get('query_params') or None, json=case.get('body') or {{}}, headers=case.get('headers') or None, timeout=10)")
    lines.extend([
        "    # 异常用例兼容两类错误响应：HTTP 4xx/5xx，或 HTTP 200 但业务 code 非 200。",
        "    def _is_error_response(resp):",
        "        if resp.status_code >= 400:",
        "            return True",
        "        try:",
        "            data = resp.json()",
        "        except Exception:",
        "            return False",
        "        if not isinstance(data, dict) or 'code' not in data:",
        "            return False",
        "        code = data.get('code')",
        "        try:",
        "            return int(code) != 200",
        "        except Exception:",
        "            return str(code).strip() not in {'', '200'}",
        "    assert _is_error_response(response), f'异常用例未进入错误响应，HTTP={response.status_code}, body={response.text[:500]}'",
    ])
    return "\n".join(lines) + "\n"


def _can_infer_normal_case(code_info: Dict[str, Any]) -> bool:
    if not code_info or not code_info.get("matched"):
        return False
    if 200 in (code_info.get("business_codes") or []) or 200 in (code_info.get("status_codes") or []):
        return True
    snippet = code_info.get("logic_snippet") or ""
    return "Result.ok" in snippet or "success" in snippet.lower()


def _success_cases(log_cases: List[Dict[str, Any]], code_info: Dict[str, Any], limit: int = None) -> List[Dict[str, Any]]:
    """挑选可作为正常基线的成功日志样本。

    与异常样本不同，正常样本要求：
    - HTTP 状态码小于 400；
    - path 参数不能是 None/null/undefined；
    - 不能命中代码里明显的异常分支常量。
    """
    limit = limit or MAX_NORMAL_CASES_PER_API
    selected: List[Dict[str, Any]] = []
    seen = set()
    for case in log_cases or []:
        if not _is_good_success_case(case, code_info):
            continue
        key = (
            str(case.get("path") or ""),
            json.dumps(normalize_params(case.get("query_params") or {}), ensure_ascii=False, sort_keys=True),
            json.dumps(parse_json_like(case.get("body") or {}), ensure_ascii=False, sort_keys=True, default=str),
        )
        if key in seen:
            continue
        selected.append(case)
        seen.add(key)
        if len(selected) >= limit:
            break
    return selected


def build_normal_test_code(
    method: str,
    path: str,
    log_cases: List[Dict[str, Any]],
    code_info: Dict[str, Any],
    max_cases: int = None,
) -> str:
    """生成正常基线用例。

    规则：
    1. 有成功日志时，优先使用真实成功日志，最多保留 max_cases 条。
    2. 没有成功日志时，根据 Swagger/代码扫描参数规则构造 1 条正常基线。
    3. 对新增类 POST 接口，会对 userName、phone、email 等常见唯一字段做动态唯一化，
       避免回放日志时因为“数据已存在”导致正常用例失败。
    """
    success_cases = _success_cases(log_cases, code_info, max_cases)
    normal_rows: List[Dict[str, Any]] = []

    if success_cases:
        for idx, success_case in enumerate(success_cases, 1):
            base_path, base_query, base_body, base_headers, actual_path = _build_base_request(path, [success_case], code_info)
            normal_rows.append({
                "id": f"normal_{idx}",
                "path_params": base_path,
                "query_params": base_query,
                "body": base_body,
                "headers": base_headers,
                "actual_path": actual_path,
                "expected_status": int(success_case.get("http_status") or 200),
                "expected_body": parse_json_like(success_case.get("response_body") or {}),
            })
    else:
        base_path, base_query, base_body, base_headers, actual_path = _build_base_request(path, [], code_info)
        normal_rows.append({
            "id": "normal_baseline",
            "path_params": base_path,
            "query_params": base_query,
            "body": base_body,
            "headers": base_headers,
            "actual_path": actual_path,
            "expected_status": 200,
            "expected_body": {"code": 200},
        })

    method_lower = method.lower()
    lines = [
        "",
        "# 正常基线用例：每个接口至少保留一条，日志存在多个成功样本时可扩展多条。",
    ]

    if _needs_unique_body(method, path):
        lines.extend([
            "from api_test_utils import make_unique_body",
            "",
        ])

    lines.extend([
        "AUTO_NORMAL_CASES = " + render_value(normal_rows),
        "",
        "@pytest.mark.parametrize(\"case\", AUTO_NORMAL_CASES, ids=[c['id'] for c in AUTO_NORMAL_CASES])",
        f"def test_auto_normal_{safe_name(method)}_{safe_name(path)}(case):",
        f"    url_path = {render_value(path)}",
        "    if case.get('actual_path'):",
        "        url_path = case.get('actual_path')",
        "    else:",
        "        for key, value in case.get('path_params', {}).items():",
        "            url_path = url_path.replace('{' + str(key) + '}', str(value))",
        "    url = f'{BASE_URL}{url_path}'",
    ])

    if method.upper() in {"GET", "DELETE"}:
        lines.append(f"    response = requests.{method_lower}(url, params=case.get('query_params') or None, headers=case.get('headers') or None, timeout=10)")
    else:
        if _needs_unique_body(method, path):
            lines.append("    payload = make_unique_body(case.get('body') or {})")
        else:
            lines.append("    payload = case.get('body') or {}")
        lines.append(f"    response = requests.{method_lower}(url, params=case.get('query_params') or None, json=payload, headers=case.get('headers') or None, timeout=10)")

    lines.append("    assert response.status_code == int(case.get('expected_status') or 200)")
    lines.append("    expected_body = case.get('expected_body') or {}")
    lines.append("    if isinstance(expected_body, dict) and 'code' in expected_body:")
    lines.append("        data = response.json()")
    lines.append("        assert data.get('code') == expected_body.get('code')")
    return "\n".join(lines) + "\n"

