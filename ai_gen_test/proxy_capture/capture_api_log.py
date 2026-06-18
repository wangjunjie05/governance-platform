"""mitmproxy 接口流量采集脚本。

启动：
    mitmdump -p 8888 -s proxy_capture/capture_api_log.py

默认输出：
    proxy_capture/logs/api_access.log

说明：
    - 默认不强制 /dev-api 前缀，兼容前后端分离和不分离项目。
    - 如只想采集某类接口，可设置 API_LOG_PATH_PREFIX=/dev-api/ 或 /system/。
    - 默认保留 Cookie 中的 JSESSIONID，便于真实项目回放 Session 认证。
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from mitmproxy import http


LOG_FILE = Path(os.getenv("PROXY_API_LOG_FILE", "proxy_capture/logs/api_access.log"))
# 默认不过滤路径，避免不分离项目的 /system/user/list、/login 等接口被漏采。
API_PATH_PREFIX = os.getenv("API_LOG_PATH_PREFIX", "").strip()
GATEWAY_PREFIXES = [x.strip().rstrip("/") for x in os.getenv("API_GATEWAY_PREFIXES", "/dev-api,/prod-api").split(",") if x.strip()]
MAX_BODY_LEN = int(os.getenv("API_LOG_MAX_BODY_LEN", "20000"))
# HTML 页面体通常很大，且对接口生成帮助有限，单独限制长度。
MAX_HTML_BODY_LEN = int(os.getenv("API_LOG_MAX_HTML_BODY_LEN", "2000"))
KEEP_AUTHORIZATION = os.getenv("API_LOG_KEEP_AUTHORIZATION", "1") == "1"
# 真实项目常见登录后通过 Cookie: JSESSIONID=... 认证。默认只保留 JSESSIONID，其他 Cookie 仍脱敏。
KEEP_JSESSIONID = os.getenv("API_LOG_KEEP_JSESSIONID", "1") == "1"
KEEP_COOKIE_NAMES = [x.strip() for x in os.getenv("API_LOG_KEEP_COOKIE_NAMES", "JSESSIONID").split(",") if x.strip()]

BINARY_TYPES = (
    "application/octet-stream",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument",
    "application/zip",
    "application/pdf",
    "image/",
)
SENSITIVE_KEYS = {"password", "pwd", "token", "access_token", "refresh_token", "cookie", "set-cookie", "secret"}


def _is_sensitive_key(key: str) -> bool:
    lower = (key or "").lower()
    if lower == "authorization":
        return not KEEP_AUTHORIZATION
    return lower in SENSITIVE_KEYS


def _sanitize_cookie(value: Any) -> Any:
    """只保留允许复用的 Cookie，默认保留 JSESSIONID。

    这样既能支持 JSESSIONID 认证回放，又避免把完整 Cookie 全量写进日志。
    """
    if not KEEP_JSESSIONID:
        return "***"
    text = str(value or "")
    kept = []
    allow = {name.lower() for name in KEEP_COOKIE_NAMES}
    for item in text.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        name, val = item.split("=", 1)
        if name.strip().lower() in allow and val.strip():
            kept.append(f"{name.strip()}={val.strip()}")
    return "; ".join(kept) if kept else "***"


def _mask_value(key: str, value: Any) -> Any:
    lower = (key or "").lower()
    if lower == "cookie":
        return _sanitize_cookie(value)
    return "***" if _is_sensitive_key(key) else value


def _mask(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: _mask(_mask_value(str(k), v)) for k, v in data.items()}
    if isinstance(data, list):
        return [_mask(v) for v in data]
    return data


def _content_type(headers: Any) -> str:
    try:
        return str(headers.get("content-type", "") or headers.get("Content-Type", "")).lower()
    except Exception:
        return ""


def _is_binary_content(content_type: str) -> bool:
    return any(content_type.startswith(x) or x in content_type for x in BINARY_TYPES)


def _truncate_text(text: str, limit: int) -> str:
    if limit <= 0:
        return text
    if len(text) <= limit:
        return text
    return text[:limit] + f"...【已截断，原长度 {len(text)} 字符】"


def _parse_form(text: str) -> dict[str, Any] | None:
    if not text or "=" not in text:
        return None
    parsed = parse_qs(text, keep_blank_values=True)
    if not parsed:
        return None
    result: dict[str, Any] = {}
    for key, values in parsed.items():
        key = unquote(str(key))
        values = [unquote(str(v)) for v in values]
        result[key] = values[0] if len(values) == 1 else values
    return result


def _looks_like_json(text: str) -> bool:
    stripped = (text or "").lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


def _parse_body(text: str, content_type: str) -> Any:
    """解析请求/响应体。

    注意：只有明确是表单时才按 form 解析，避免 HTML 中的 a=b、JS 片段被误解析成畸形 dict。
    """
    if not text:
        return None
    if "multipart/form-data" in content_type:
        return {"_body_omitted": True, "_reason": "multipart_form_data"}
    if _is_binary_content(content_type):
        return {"_body_omitted": True, "_reason": "binary_content", "_content_type": content_type}

    text = text.strip()
    if not text:
        return None

    is_json_type = "application/json" in content_type or "+json" in content_type
    if is_json_type or _looks_like_json(text):
        try:
            return json.loads(text)
        except Exception:
            # JSON 声明异常时保留原文预览，便于排查后端返回异常内容。
            return _truncate_text(unquote(text), MAX_BODY_LEN)

    if "application/x-www-form-urlencoded" in content_type:
        form = _parse_form(text)
        if form is not None:
            return form

    text = unquote(text)
    if "text/html" in content_type:
        return _truncate_text(text, MAX_HTML_BODY_LEN)
    return _truncate_text(text, MAX_BODY_LEN)


def _query_params(query: str) -> dict[str, Any]:
    parsed = parse_qs(query or "", keep_blank_values=True)
    result: dict[str, Any] = {}
    for key, values in parsed.items():
        key = unquote(str(key))
        values = [unquote(str(v)) for v in values]
        value = values[0] if len(values) == 1 else values
        result[key] = _mask_value(key, value)
    return result


def _headers(headers: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in headers.items():
        result[str(key)] = _mask_value(str(key), str(value))
    return result


def _get_header(headers: Any, name: str) -> str:
    try:
        return str(headers.get(name, "") or headers.get(name.lower(), "") or headers.get(name.upper(), ""))
    except Exception:
        return ""


def _infer_auth_type(headers: Any) -> str:
    """识别本次请求主要使用的认证方式，便于后续生成脚本选择回放头。"""
    cookie = _get_header(headers, "Cookie")
    if re.search(r"(?:^|;\s*)JSESSIONID=", cookie, flags=re.I):
        return "jsessionid_cookie"
    if _get_header(headers, "Authorization"):
        return "authorization"
    for name in ("X-Token", "token", "access_token", "isToken"):
        if _get_header(headers, name):
            return name.lower()
    if cookie:
        return "cookie"
    return "none"


def _strip_gateway(path: str) -> tuple[str, str]:
    path = unquote(path or "/")
    for prefix in sorted(GATEWAY_PREFIXES, key=len, reverse=True):
        if path == prefix:
            return prefix, "/"
        if path.startswith(prefix + "/"):
            return prefix, path[len(prefix):] or "/"
    return "", path


def _infer_path_template(path: str) -> str:
    _, path = _strip_gateway(path)
    parts = [p for p in path.split("/") if p]
    out = []
    for part in parts:
        part = unquote(part)
        if re.fullmatch(r"\d+", part) or re.fullmatch(r"\d+(,\d+)+", part):
            out.append("{id}")
        elif re.fullmatch(r"[A-Za-z]{2,}\d{3,}.*", part) or re.fullmatch(r"[0-9a-fA-F]{8,}", part):
            out.append("{id}")
        else:
            out.append(part)
    return "/" + "/".join(out) if out else "/"


def response(flow: http.HTTPFlow) -> None:
    if not flow.response:
        return

    parsed = urlparse(flow.request.pretty_url)
    raw_path = unquote(parsed.path or "/")
    if API_PATH_PREFIX and not raw_path.startswith(API_PATH_PREFIX):
        return

    req_ct = _content_type(flow.request.headers)
    resp_ct = _content_type(flow.response.headers)

    try:
        req_text = flow.request.get_text(strict=False)
    except Exception:
        req_text = ""
    try:
        resp_text = "" if _is_binary_content(resp_ct) else flow.response.get_text(strict=False)
    except Exception:
        resp_text = ""

    gateway_prefix, normalized_path = _strip_gateway(raw_path)
    response_body = _mask(_parse_body(resp_text, resp_ct))
    record = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "mitmproxy",
        "method": flow.request.method,
        "scheme": parsed.scheme,
        "host": parsed.netloc,
        "gateway_prefix": gateway_prefix,
        "path": raw_path,
        "normalized_path": normalized_path,
        "path_template": _infer_path_template(raw_path),
        "url": unquote(flow.request.pretty_url),
        "query_params": _query_params(parsed.query),
        "request_content_type": req_ct,
        "request_headers": _headers(flow.request.headers),
        "auth_type": _infer_auth_type(flow.request.headers),
        "request_body": _mask(_parse_body(req_text, req_ct)) or {},
        "http_status": flow.response.status_code,
        "response_content_type": resp_ct,
        "response_headers": _headers(flow.response.headers),
        "response_body": response_body if response_body is not None else {},
        "duration_ms": int((flow.response.timestamp_end - flow.request.timestamp_start) * 1000)
        if flow.response.timestamp_end and flow.request.timestamp_start else None,
    }
    if isinstance(response_body, dict):
        record["business_code"] = response_body.get("code")
    else:
        record["business_code"] = None

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str))
        f.write("\n")
