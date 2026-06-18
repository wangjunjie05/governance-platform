from pathlib import Path

CONFTST_CODE = r'''
import json
import os
from pathlib import Path

import pytest
import requests

_CURRENT_TEST = None
_CASE_DATA = {}
_ORIGINAL_REQUEST = requests.sessions.Session.request
_AUTH_TOKEN_CACHE = None
_AUTH_REFRESHING = False


def _safe_json_response(resp):
    try:
        return resp.json()
    except Exception:
        try:
            text = resp.text
            return text[:5000] if isinstance(text, str) else text
        except Exception:
            return ""


def _safe_body(kwargs):
    if "json" in kwargs:
        return kwargs.get("json")
    if "data" in kwargs:
        return kwargs.get("data")
    if "files" in kwargs:
        files = kwargs.get("files") or {}
        if isinstance(files, dict):
            return {k: "<file>" for k in files.keys()}
        return "<files>"
    return None


def _json_get(data, path):
    cur = data
    for part in str(path or "").split("."):
        if not part:
            continue
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur.get(part)
    return cur


def _extract_token(data):
    paths = [p.strip() for p in os.getenv("AUTH_TOKEN_JSON_PATHS", "token,data.token,access_token,data.access_token").split(",") if p.strip()]
    for path in paths:
        value = _json_get(data, path)
        if value:
            return str(value)
    return None


def _login_for_token():
    global _AUTH_TOKEN_CACHE, _AUTH_REFRESHING
    if _AUTH_REFRESHING:
        return None

    username = os.getenv("AUTH_USERNAME", "").strip()
    password = os.getenv("AUTH_PASSWORD", "").strip()
    login_path = os.getenv("AUTH_LOGIN_PATH", "/login").strip() or "/login"
    if not username or not password:
        return None

    base_url = os.getenv("BASE_URL", "").rstrip("/")
    if not base_url:
        return None

    username_field = os.getenv("AUTH_USERNAME_FIELD", "username")
    password_field = os.getenv("AUTH_PASSWORD_FIELD", "password")
    payload = {username_field: username, password_field: password}

    try:
        _AUTH_REFRESHING = True
        resp = _ORIGINAL_REQUEST(requests.Session(), "POST", base_url + login_path, json=payload, timeout=15)
        data = _safe_json_response(resp)
        token = _extract_token(data) if isinstance(data, dict) else None
        if token:
            prefix = os.getenv("AUTH_HEADER_PREFIX", "Bearer").strip()
            _AUTH_TOKEN_CACHE = f"{prefix} {token}" if prefix and not token.lower().startswith(prefix.lower() + " ") else token
            return _AUTH_TOKEN_CACHE
    except Exception:
        return None
    finally:
        _AUTH_REFRESHING = False
    return None


def _replay_headers():
    raw = os.getenv("TEST_REPLAY_HEADERS", "").strip()
    headers = {}
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                headers.update({str(k): v for k, v in data.items() if v not in (None, "")})
        except Exception:
            pass

    # 兼容旧环境变量。
    latest_auth = os.getenv("TEST_AUTHORIZATION", "").strip()
    if latest_auth and not any(str(k).lower() == "authorization" for k in headers):
        headers["Authorization"] = latest_auth

    if _AUTH_TOKEN_CACHE:
        headers = {k: v for k, v in headers.items() if str(k).lower() != "authorization"}
        headers["Authorization"] = _AUTH_TOKEN_CACHE
    return headers


def _merge_replay_headers(kwargs):
    replay = _replay_headers()
    if not replay:
        return

    headers = dict(kwargs.get("headers") or {})
    existing_lower = {str(k).lower(): k for k in headers.keys()}
    cookie_first = os.getenv("AUTH_COOKIE_FIRST", "1").strip().lower() in {"1", "true", "yes", "y"}
    replay_has_jsessionid = any(
        str(k).lower() == "cookie" and "jsessionid=" in str(v).lower()
        for k, v in replay.items()
    )

    if cookie_first and replay_has_jsessionid:
        # JSESSIONID 认证项目以 Cookie 为准，清理生成脚本中可能写死的旧 token。
        for old_key in list(headers.keys()):
            if str(old_key).lower() in {"authorization", "x-token", "token", "access_token"}:
                headers.pop(old_key, None)
        existing_lower = {str(k).lower(): k for k in headers.keys()}

    for key, value in replay.items():
        low = str(key).lower()
        if low == "cookie" and replay_has_jsessionid:
            # Cookie/JSESSIONID 使用日志中最新值覆盖旧值。
            old_key = existing_lower.get(low)
            if old_key is not None:
                headers.pop(old_key, None)
            headers[key] = value
        elif low == "authorization":
            # Authorization 使用日志中最新值覆盖旧值；但 Cookie 优先时已在上游过滤。
            old_key = existing_lower.get(low)
            if old_key is not None:
                headers.pop(old_key, None)
            headers[key] = value
        elif low not in existing_lower:
            # 其他认证头只在生成代码未显式设置时补充，避免破坏接口特殊请求头。
            headers[key] = value
    kwargs["headers"] = headers


def _patched_request(self, method, url, **kwargs):
    _merge_replay_headers(kwargs)

    resp = _ORIGINAL_REQUEST(self, method, url, **kwargs)

    if getattr(resp, "status_code", None) == 401 and os.getenv("AUTH_ENABLE_REFRESH", "0") == "1":
        new_auth = _login_for_token()
        if new_auth:
            headers = dict(kwargs.get("headers") or {})
            headers = {k: v for k, v in headers.items() if str(k).lower() != "authorization"}
            headers["Authorization"] = new_auth
            kwargs["headers"] = headers
            resp = _ORIGINAL_REQUEST(self, method, url, **kwargs)

    global _CURRENT_TEST
    if _CURRENT_TEST:
        _CASE_DATA[_CURRENT_TEST] = {
            "method": str(method).upper(),
            "url": str(url),
            "params": kwargs.get("params"),
            "request_body": _safe_body(kwargs),
            "response_status": getattr(resp, "status_code", None),
            "response_body": _safe_json_response(resp),
        }
    return resp


def pytest_configure(config):
    requests.sessions.Session.request = _patched_request


def pytest_unconfigure(config):
    requests.sessions.Session.request = _ORIGINAL_REQUEST


def pytest_runtest_setup(item):
    global _CURRENT_TEST
    _CURRENT_TEST = item.nodeid


def _guess_case_type(nodeid, case_data):
    text = nodeid.lower()
    if "test_auto_normal" in text:
        return "正常"
    if "test_auto_exception" in text:
        return "异常"
    keywords = [
        "error", "exception", "invalid", "missing", "blank", "null",
        "fail", "wrong", "empty", "not_found", "notfound", "too_",
        "超过", "错误", "异常", "为空", "缺少", "不存在",
    ]
    if any(k in text for k in keywords):
        return "异常"
    status = case_data.get("response_status")
    try:
        if int(status) >= 400:
            return "异常"
    except Exception:
        pass
    return "正常"


def pytest_runtest_logreport(report):
    if report.when != "call":
        return

    case_data = _CASE_DATA.get(report.nodeid, {})
    result = "passed" if report.passed else "failed" if report.failed else "skipped"
    row = {
        "nodeid": report.nodeid,
        "test_name": report.nodeid.split("::")[-1],
        "case_type": _guess_case_type(report.nodeid, case_data),
        "result": result,
        "duration_s": round(float(getattr(report, "duration", 0) or 0), 4),
        "method": case_data.get("method", ""),
        "url": case_data.get("url", ""),
        "params": case_data.get("params"),
        "request_body": case_data.get("request_body"),
        "response_status": case_data.get("response_status"),
        "response_body": case_data.get("response_body"),
        "error_msg": str(report.longrepr) if report.failed else "",
    }
    out_file = os.getenv("PYTEST_CASE_REPORT_JSONL")
    if out_file:
        Path(out_file).parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
'''

API_TEST_UTILS_CODE = r'''
import io
import os
import time
from typing import Any, Dict

import requests


BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8080").rstrip("/")


def make_unique_body(body: Dict[str, Any]) -> Dict[str, Any]:
    body = dict(body or {})
    suffix = str(int(time.time() * 1000))
    unique_fields = [
        "userName", "username", "loginName", "nickName", "phonenumber", "phone", "mobile", "email",
        "roleKey", "roleName", "deptName", "postCode", "postName", "configKey", "configName", "dictName", "dictType",
    ]
    for key in unique_fields:
        value = body.get(key)
        if not isinstance(value, str) or not value:
            continue
        if key.lower() == "email":
            body[key] = "auto_" + suffix + "@example.com"
        elif key.lower() in {"phone", "mobile", "phonenumber"}:
            body[key] = "13" + suffix[-9:].rjust(9, "0")
        else:
            body[key] = value + "_" + suffix[-6:]
    return body


def memory_file(filename: str = "test.xlsx", content_type: str = "application/octet-stream", content: bytes = b"test"):
    return (filename, io.BytesIO(content), content_type)


def assert_status(response, expected_status: int):
    assert response.status_code == int(expected_status)


def safe_json(response):
    try:
        return response.json()
    except Exception:
        return {}
'''


def write_conftest(tests_dir: str) -> None:
    Path(tests_dir).mkdir(parents=True, exist_ok=True)
    (Path(tests_dir) / "conftest.py").write_text(CONFTST_CODE, encoding="utf-8")
    (Path(tests_dir) / "api_test_utils.py").write_text(API_TEST_UTILS_CODE, encoding="utf-8")
