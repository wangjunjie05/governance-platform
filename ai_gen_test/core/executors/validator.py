import json
import os
import py_compile
import re
import subprocess
from typing import Any, Dict, Tuple

from core.config import PYTEST_TIMEOUT


def check_syntax(file_path: str) -> Tuple[bool, str]:
    try:
        py_compile.compile(file_path, doraise=True)
        return True, ""
    except Exception as e:
        return False, str(e)


def parse_pytest_counts(output: str) -> Dict[str, int]:
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    if not output:
        return counts

    patterns = {
        "passed": r"(\d+)\s+passed",
        "failed": r"(\d+)\s+failed",
        "errors": r"(\d+)\s+errors?",
        "skipped": r"(\d+)\s+skipped",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, output)
        if match:
            counts[key] = int(match.group(1))
    return counts


def check_pytest(file_path: str, report_path: str = None, case_jsonl_path: str = None, base_url: str = None, replay_headers: Dict[str, Any] = None) -> Tuple[bool, str, Dict[str, int]]:
    try:
        env = os.environ.copy()
        if case_jsonl_path:
            if os.path.exists(case_jsonl_path):
                os.remove(case_jsonl_path)
            env["PYTEST_CASE_REPORT_JSONL"] = case_jsonl_path
        if base_url:
            env["BASE_URL"] = base_url.rstrip("/")

        # 将日志中最新可复用认证请求头注入 pytest 插件。
        # TEST_REPLAY_HEADERS 支持 Authorization、X-Token、Cookie、isToken 等多种认证位置；
        # TEST_AUTHORIZATION 保留旧逻辑兼容。
        if replay_headers:
            env["TEST_REPLAY_HEADERS"] = json.dumps(replay_headers, ensure_ascii=False, default=str)
            for key, value in replay_headers.items():
                if str(key).lower() == "authorization" and value:
                    env["TEST_AUTHORIZATION"] = str(value)
                    break

        # 默认不自动登录刷新 token；需要时由 AUTH_ENABLE_REFRESH 显式开启。
        enable_refresh = os.getenv("AUTH_ENABLE_REFRESH", "0").strip().lower() in {"1", "true", "yes", "y"}
        env["AUTH_ENABLE_REFRESH"] = "1" if enable_refresh else "0"
        auth_login_path = os.getenv("AUTH_LOGIN_PATH", "/login")
        auth_username = os.getenv("AUTH_USERNAME", "")
        auth_password = os.getenv("AUTH_PASSWORD", "")
        if auth_login_path:
            env["AUTH_LOGIN_PATH"] = auth_login_path
        if auth_username:
            env["AUTH_USERNAME"] = auth_username
        if auth_password:
            env["AUTH_PASSWORD"] = auth_password
        env["AUTH_USERNAME_FIELD"] = os.getenv("AUTH_USERNAME_FIELD", "username")
        env["AUTH_PASSWORD_FIELD"] = os.getenv("AUTH_PASSWORD_FIELD", "password")
        env["AUTH_TOKEN_JSON_PATHS"] = os.getenv("AUTH_TOKEN_JSON_PATHS", "token,data.token,access_token,data.access_token")

        result = subprocess.run(
            ["pytest", file_path, "-q", "--tb=short", "-rA"],
            capture_output=True,
            text=True,
            timeout=PYTEST_TIMEOUT,
            env=env,
        )
        output = (result.stdout + "\n" + result.stderr).strip()
        counts = parse_pytest_counts(output)

        if report_path:
            os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(output + "\n")

        if result.returncode == 0:
            return True, "", counts
        return False, output, counts
    except Exception as e:
        error_msg = str(e)
        if report_path:
            os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(error_msg + "\n")
        return False, error_msg, {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
