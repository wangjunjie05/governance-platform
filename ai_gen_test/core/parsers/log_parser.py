import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, unquote

from core.utils.common import build_key
from core.config import LOG_FILE, API_GATEWAY_PREFIXES


HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
STATIC_SUFFIXES = (
    ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".map", ".html",
)

# 网关前缀来自 core.config。前后端不分离项目可配置 gateway_prefixes: ""，此时不会剥离 /dev-api。

def normalize_log_path(path: str) -> str:
    """兜底归一化：把真实访问路径粗略转成可匹配 Swagger 的模板路径。

    示例：
        /dev-api/system/user/1 -> /dev-api/system/user/{id}
        /system/user/1,2      -> /system/user/{id}
        /order/ORD202606001   -> /order/{id}
    """
    path = unquote(urlparse(path or "").path)
    parts = []
    for part in path.split("/"):
        if not part:
            parts.append(part)
            continue
        if part.isdigit() or re.fullmatch(r"\d+(,\d+)+", part):
            parts.append("{id}")
        elif re.fullmatch(r"[A-Za-z]{2,}\d{3,}.*", part):
            parts.append("{id}")
        else:
            parts.append(part)
    return "/".join(parts) or path


def split_gateway_prefix(path: str) -> Tuple[str, str]:
    """拆出网关前缀。

    例如 RuoYi 前端代理日志里是 /dev-api/system/user，Swagger 里通常是 /system/user。
    这里返回：
        ("/dev-api", "/system/user")
    这样日志可以命中 Swagger 接口，同时运行测试时 BASE_URL 可以自动使用
    http://host:port/dev-api。
    """
    clean_path = unquote(urlparse(path or "").path or "/")
    for prefix in sorted(API_GATEWAY_PREFIXES, key=len, reverse=True):
        if not prefix:
            continue
        if clean_path == prefix:
            return prefix, "/"
        if clean_path.startswith(prefix + "/"):
            stripped = clean_path[len(prefix):] or "/"
            return prefix, stripped
    return "", clean_path


def _origin(item: Dict[str, Any]) -> str:
    url = item.get("url")
    if url:
        parsed = urlparse(str(url))
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    scheme = item.get("scheme") or "http"
    host = item.get("host") or ""
    return f"{scheme}://{host}" if host else ""


def _extract_json_from_line(line: str) -> Optional[Dict[str, Any]]:
    """兼容纯 JSONL 和 Spring 普通日志前缀 + JSON。"""
    line = line.strip()
    if not line:
        return None

    try:
        obj = json.loads(line)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    if "API_ACCESS_LOG" not in line and '"method"' not in line:
        return None

    start = line.find("{")
    end = line.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        obj = json.loads(line[start:end + 1])
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _parse_body(value: Any) -> Any:
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
            return text
    return value


def _decode_value(value: Any) -> Any:
    if isinstance(value, str):
        return unquote(value)
    if isinstance(value, list):
        return [_decode_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _decode_value(v) for k, v in value.items()}
    return value


def _normalize_query_params(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, val in value.items():
        if isinstance(val, list) and len(val) == 1:
            result[key] = _decode_value(val[0])
        else:
            result[key] = _decode_value(val)
    return result


def _is_api_access_item(item: Dict[str, Any]) -> bool:
    method = str(item.get("method", "")).upper()
    raw_path = str(item.get("path") or item.get("uri") or "")
    path = urlparse(raw_path).path
    if method not in HTTP_METHODS or not path.startswith("/"):
        return False
    if path.endswith(STATIC_SUFFIXES):
        return False
    # 过滤前端页面和常见静态资源请求，保留 /system/user、/dev-api/system/user 这类业务接口。
    first = path.strip("/").split("/", 1)[0]
    if first in {"assets", "static", "css", "js", "img", "fonts"}:
        return False
    return True


def _extract_path_params(path_template: str, actual_path: str) -> Dict[str, Any]:
    if not path_template or not actual_path or "{" not in path_template:
        return {}

    template_parts = urlparse(path_template).path.strip("/").split("/")
    actual_parts = urlparse(actual_path).path.strip("/").split("/")
    if len(template_parts) != len(actual_parts):
        return {}

    params: Dict[str, Any] = {}
    for template_part, actual_part in zip(template_parts, actual_parts):
        match = re.fullmatch(r"\{([^/{}]+)\}", template_part)
        if match:
            params[match.group(1)] = actual_part
        elif template_part != actual_part:
            return {}
    return params


def load_api_logs(log_file: str = LOG_FILE) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    if not os.path.exists(log_file):
        return grouped

    seq = 0
    with open(log_file, "r", encoding="utf-8", errors="ignore") as file:
        for line in file:
            seq += 1
            item = _extract_json_from_line(line)
            if not item or not _is_api_access_item(item):
                continue

            method = str(item.get("method", "")).upper()
            original_path = unquote(str(item.get("path") or item.get("uri") or ""))
            gateway_prefix, clean_path = split_gateway_prefix(original_path)

            raw_template = unquote(str(item.get("path_template") or normalize_log_path(original_path)))
            template_prefix, clean_template = split_gateway_prefix(str(raw_template))
            gateway_prefix = gateway_prefix or template_prefix
            path_template = clean_template or clean_path

            origin = _origin(item)
            base_url = f"{origin}{gateway_prefix}" if origin else ""
            key = build_key(method, path_template)

            case = {
                "method": method,
                "path": clean_path,
                "original_path": original_path,
                "path_template": path_template,
                "original_path_template": raw_template,
                "gateway_prefix": gateway_prefix,
                "base_url": base_url,
                "path_params": item.get("path_params") or _extract_path_params(path_template, clean_path),
                "query_params": _normalize_query_params(item.get("query_params") or {}),
                "headers": item.get("request_headers") or item.get("headers") or {},
                "body": _parse_body(item.get("request_body") or item.get("body") or {}),
                "http_status": item.get("http_status") or item.get("status"),
                "business_code": item.get("business_code"),
                "response_body": item.get("response_body"),
                "time": item.get("time"),
                "_seq": seq,
            }
            grouped.setdefault(key, []).append(case)
    return grouped


def pick_log_cases(log_cases: List[Dict[str, Any]], max_cases: int = 3) -> List[Dict[str, Any]]:
    selected = []
    seen_status = set()
    for case in log_cases:
        status = case.get("http_status")
        if status not in seen_status:
            selected.append(case)
            seen_status.add(status)
        if len(selected) >= max_cases:
            break
    return selected or log_cases[:max_cases]


def _swagger_path_to_regex(path_template: str) -> re.Pattern:
    escaped = re.escape(path_template)
    escaped = re.sub(r"\\\{[^/]+?\\\}", r"[^/]+", escaped)
    return re.compile(r"^" + escaped + r"/?$")


def find_log_cases_for_endpoint(log_map: Dict[str, List[Dict[str, Any]]], method: str, swagger_path: str) -> List[Dict[str, Any]]:
    key = build_key(method, swagger_path)
    if key in log_map:
        return log_map[key]

    method = method.upper()
    path_re = _swagger_path_to_regex(swagger_path)
    matched: List[Dict[str, Any]] = []
    for log_key, cases in log_map.items():
        if not log_key.startswith(method + " "):
            continue
        for case in cases:
            path = str(case.get("path") or "")
            path_template = str(case.get("path_template") or "")
            if path_re.match(path) or path_template.rstrip("/") == swagger_path.rstrip("/"):
                matched.append(case)
    return matched



def extract_replay_headers_from_logs(log_map: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """从代理日志里提取最近一次可复用请求头。

    真实项目常见登录后通过 Cookie: JSESSIONID=... 认证。默认 Cookie 优先：
    如果日志中存在有效 JSESSIONID，则优先回放 Cookie，并丢弃可能过期的 Authorization/token，
    避免旧 token 干扰以 session 为主的系统。若没有 Cookie/JSESSIONID，则继续兼容
    Authorization、X-Token、token、access_token 等 token 认证方式。
    """
    raw_names = os.getenv(
        "AUTH_REPLAY_HEADER_NAMES",
        "Cookie,Authorization,X-Token,token,access_token,isToken,repeatSubmit",
    )
    allow = {str(x).strip().lower() for x in raw_names.split(",") if str(x).strip()}
    # 运行环境未配置时保留兜底列表。
    if not allow:
        allow = {"cookie", "authorization", "x-token", "token", "access_token", "istoken", "repeatsubmit"}

    cookie_first = os.getenv("AUTH_COOKIE_FIRST", "1").strip().lower() in {"1", "true", "yes", "y"}
    latest: Dict[str, Tuple[int, str, Any]] = {}

    for cases in log_map.values():
        for case in cases:
            seq = int(case.get("_seq") or 0)
            headers = case.get("headers") or case.get("request_headers") or {}
            if not isinstance(headers, dict):
                continue
            for key, value in headers.items():
                original_key = str(key)
                low = original_key.lower()
                if low in allow and value not in (None, "", "***"):
                    old = latest.get(low)
                    if old is None or seq >= old[0]:
                        latest[low] = (seq, original_key, value)

    result = {original_key: value for _, original_key, value in latest.values()}

    def _has_jsessionid_cookie(headers: Dict[str, Any]) -> bool:
        for key, value in headers.items():
            if str(key).lower() == "cookie" and "jsessionid=" in str(value).lower():
                return True
        return False

    if cookie_first and _has_jsessionid_cookie(result):
        # JSESSIONID 系统以 Cookie 为主，避免把旧 Authorization/token 一起带过去造成干扰。
        token_like = {"authorization", "x-token", "token", "access_token"}
        result = {k: v for k, v in result.items() if str(k).lower() not in token_like}

    return result

def infer_base_url_from_logs(log_map: Dict[str, List[Dict[str, Any]]]) -> str:
    for cases in log_map.values():
        for case in cases:
            base_url = str(case.get("base_url") or "").strip()
            if base_url:
                return base_url.rstrip("/")
    return ""
