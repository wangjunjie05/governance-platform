"""上下文信息收集模块。"""
from typing import Any, Dict, List, Tuple

from core.analyzers.code_scanner import scan_code_for_endpoint
from core.config import CODE_DIR, MAX_NORMAL_CASES_PER_API
from core.analyzers.exception_case_generator import build_exception_cases
from core.parsers.log_parser import find_log_cases_for_endpoint, pick_log_cases


def collect_context(
    spec: Dict[str, Any],
    path: str,
    method: str,
    op: Dict[str, Any],
    log_map: Dict[str, List[Dict[str, Any]]],
    mode: str,
    exception_mode: str,
    code_dir: str = None,
    code_include=None,
    code_exclude=None,
    default_headers: Dict[str, Any] = None,
    code_scan_cache: Dict[str, Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    """收集接口生成所需的上下文信息。
    
    返回：(log_cases, code_info, exception_cases)
    """
    if mode == "swagger_code_log":
        log_cases = pick_log_cases(find_log_cases_for_endpoint(log_map, method, path), max_cases=max(MAX_NORMAL_CASES_PER_API + 3, 6))
    else:
        log_cases = []

    if mode in {"swagger_code", "swagger_code_log"}:
        cache_key = f"{code_dir or CODE_DIR}|{method.upper()}|{path}|{code_include}|{code_exclude}"
        if code_scan_cache is not None and cache_key in code_scan_cache:
            code_info = dict(code_scan_cache[cache_key])
        else:
            code_info = scan_code_for_endpoint(code_dir or CODE_DIR, path, method, include_keywords=code_include, exclude_keywords=code_exclude)
            if code_scan_cache is not None:
                code_scan_cache[cache_key] = dict(code_info)
    else:
        code_info = {"matched": False, "validation_rules": []}

    code_info = _merge_swagger_rules(code_info, _swagger_validation_rules(spec, path, op))
    if default_headers:
        code_info["default_headers"] = default_headers
    exception_cases = build_exception_cases(method, path, log_cases, code_info, exception_mode) if mode in {"swagger_code", "swagger_code_log"} else []
    return log_cases, code_info, exception_cases


def _swagger_value_for_schema(schema: Dict[str, Any]) -> Any:
    """根据 Swagger schema 生成一个尽量正常的默认值。"""
    if not isinstance(schema, dict):
        return "demo"
    if "example" in schema:
        return schema.get("example")
    if "default" in schema:
        return schema.get("default")
    enum_values = schema.get("enum") or []
    if enum_values:
        return enum_values[0]

    typ = str(schema.get("type") or "").lower()
    fmt = str(schema.get("format") or "").lower()
    if typ in {"integer", "int"} or fmt in {"int32", "int64"}:
        minimum = schema.get("minimum")
        if minimum is not None:
            try:
                return int(minimum)
            except Exception:
                return 1
        return 1
    if typ == "number" or fmt in {"float", "double"}:
        minimum = schema.get("minimum")
        if minimum is not None:
            try:
                return float(minimum)
            except Exception:
                return 1
        return 1
    if typ == "boolean":
        return True
    if typ == "array":
        item = schema.get("items") or {}
        return [_swagger_value_for_schema(item)]
    if typ == "object":
        return {}
    return "demo"


def _swagger_validation_rules(spec: Dict[str, Any], path: str, op: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 Swagger/OpenAPI 中抽取生成正常基线用例需要的参数规则。
    
    这些规则不是异常校验规则，而是为了在 swagger / swagger_code 模式下，
    没有日志时也能为每个接口构造一条相对合理的正常请求。
    """
    rules: List[Dict[str, Any]] = []

    for param in op.get("parameters") or []:
        if not isinstance(param, dict):
            continue
        name = param.get("name")
        if not name:
            continue
        schema = _resolve_ref(spec, param.get("schema") or {})
        rules.append({
            "class_name": "swagger_param",
            "field": name,
            "type": schema.get("type", param.get("type", "string")) if isinstance(schema, dict) else "string",
            "annotation": "SwaggerParam",
            "location": "path" if param.get("in") == "path" else "query",
            "source_file": "swagger",
            "example": _swagger_value_for_schema(schema if isinstance(schema, dict) else {}),
        })

    request_body = op.get("requestBody") or {}
    content = request_body.get("content") or {}
    schema = None
    if "application/json" in content:
        schema = content.get("application/json", {}).get("schema")
    elif content:
        first = next(iter(content.values()))
        schema = first.get("schema") if isinstance(first, dict) else None

    if schema:
        schema = _resolve_ref(spec, schema)
        if isinstance(schema, dict):
            required = set(schema.get("required") or [])
            properties = schema.get("properties") or {}
            for field, field_schema in properties.items():
                field_schema = _resolve_ref(spec, field_schema)
                rules.append({
                    "class_name": schema.get("title", "swagger_body"),
                    "field": field,
                    "type": field_schema.get("type", "string") if isinstance(field_schema, dict) else "string",
                    "annotation": "SwaggerBody",
                    "location": "body",
                    "source_file": "swagger",
                    "required": field in required,
                    "example": _swagger_value_for_schema(field_schema if isinstance(field_schema, dict) else {}),
                })
    return rules


def _resolve_ref(spec: Dict[str, Any], obj: Any) -> Any:
    """解析 Swagger 中的 $ref 引用。"""
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


def _merge_swagger_rules(code_info: Dict[str, Any], swagger_rules: List[Dict[str, Any]]) -> Dict[str, Any]:
    """把 Swagger 参数规则补充到 code_info，供正常基线生成器使用。"""
    info = dict(code_info or {})
    existing = list(info.get("validation_rules") or [])
    seen = {(r.get("location"), r.get("field")) for r in existing}
    for rule in swagger_rules:
        key = (rule.get("location"), rule.get("field"))
        if key not in seen:
            existing.append(rule)
            seen.add(key)
    info["validation_rules"] = existing
    info.setdefault("language", "swagger")
    return info


def is_rule_executable_exception(case: Dict[str, Any]) -> bool:
    """判断异常场景是否能由程序直接构造为请求用例。"""
    return bool(case.get("field")) and case.get("location") in {"body", "query", "path"}


def count_success_log_cases(log_cases: List[Dict[str, Any]]) -> int:
    """统计成功日志用例数量。"""
    count = 0
    for case in log_cases or []:
        try:
            if int(case.get("http_status") or 0) < 400:
                count += 1
        except Exception:
            pass
    return count


def has_normal_case_rows(case_rows: List[Dict[str, Any]]) -> bool:
    """判断是否存在正常用例记录。"""
    return any(row.get("case_type") == "正常" for row in case_rows or [])
