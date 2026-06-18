import json
import re
from typing import Any, Dict, List, Optional

from core.config import BASE_URL
from core.generators.fallback_generator import (
    default_replay_headers,
    merge_with_latest_auth,
    normalize_params,
    parse_json_like,
    render_value,
    replay_headers,
)
from core.utils.common import safe_name


DOWNLOAD_KEYWORDS = ("importtemplate", "export", "download", "template")
UPLOAD_KEYWORDS = ("importdata", "avatar", "upload")
AUTH_KEYWORDS = ("captcha", "login", "logout")


def _endpoint_text(method: str, path: str) -> str:
    return f"{method or ''} {path or ''}".lower()


def endpoint_kind(method: str, path: str) -> Optional[str]:
    text = _endpoint_text(method, path)

    # importTemplate 是“下载模板”，不是上传接口，必须优先判断。
    if any(k in text for k in DOWNLOAD_KEYWORDS):
        return "download"
    if any(k in text for k in UPLOAD_KEYWORDS):
        return "upload"
    if any(k in text for k in AUTH_KEYWORDS):
        return "auth"
    return None


def is_special_endpoint(method: str, path: str) -> bool:
    return endpoint_kind(method, path) in {"download", "upload"}


def _first_case(log_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    return (log_cases or [{}])[0] or {}


def _headers(case: Dict[str, Any], code_info: Dict[str, Any]) -> Dict[str, Any]:
    headers = replay_headers(case.get("headers") or case.get("request_headers") or {})
    headers = merge_with_latest_auth(headers, default_replay_headers(code_info))
    return headers or default_replay_headers(code_info)


def _url_expr(path: str, case: Dict[str, Any]) -> str:
    actual_path = str(case.get("path") or "").strip()
    if actual_path:
        return f'f"{{BASE_URL}}{actual_path}"'

    path_params = case.get("path_params") or {}
    url_path = path
    for key, value in path_params.items():
        url_path = url_path.replace("{" + str(key) + "}", str(value))

    # 没有日志时，为路径参数补一个保守值。
    for name in re.findall(r"\{([^}]+)\}", url_path):
        lower = name.lower()
        if "user" in lower or lower.endswith("id"):
            value = 1
        else:
            value = "demo"
        url_path = url_path.replace("{" + name + "}", str(value))
    return f'f"{{BASE_URL}}{url_path}"'


def _query_params(case: Dict[str, Any]) -> Dict[str, Any]:
    return normalize_params(case.get("query_params") or {})


def _download_code(method: str, path: str, log_cases: List[Dict[str, Any]], code_info: Dict[str, Any]) -> str:
    case = _first_case(log_cases)
    status = int(case.get("http_status") or 200)
    headers = _headers(case, code_info)
    params = _query_params(case)
    method_lower = (method or "GET").lower()

    lines = [
        "import os",
        "import requests",
        "",
        f'BASE_URL = os.getenv("BASE_URL", "{BASE_URL}")',
        "",
        f"def test_{safe_name(method)}_{safe_name(path)}_download():",
        f"    url = {_url_expr(path, case)}",
        f"    headers = {render_value(headers)}",
    ]
    if params:
        lines.append(f"    params = {render_value(params)}")
        lines.append(f"    response = requests.{method_lower}(url, params=params, headers=headers or None, timeout=30)")
    else:
        lines.append(f"    response = requests.{method_lower}(url, headers=headers or None, timeout=30)")
    lines.extend([
        f"    assert response.status_code == {status}",
        "    # 下载/导出/模板接口可能返回 Excel、ZIP、PDF 或二进制流，不解析 response.json()。",
        "    assert response.content is not None",
        "",
    ])
    return "\n".join(lines)


def _upload_file_field(path: str) -> str:
    text = (path or "").lower()
    if "avatar" in text:
        return "avatarfile"
    return "file"


def _upload_file_tuple(path: str) -> str:
    text = (path or "").lower()
    if "avatar" in text:
        return '("avatar.png", io.BytesIO(b"fake-image-content"), "image/png")'
    return '("import.xlsx", io.BytesIO(b"fake-file-content"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")'


def _upload_code(method: str, path: str, log_cases: List[Dict[str, Any]], code_info: Dict[str, Any]) -> str:
    case = _first_case(log_cases)
    status = int(case.get("http_status") or 200)
    headers = _headers(case, code_info)
    params = _query_params(case)
    file_field = _upload_file_field(path)
    file_tuple = _upload_file_tuple(path)
    method_lower = (method or "POST").lower()

    # requests 自己生成 multipart boundary，不能手写 Content-Type。
    headers = {k: v for k, v in headers.items() if str(k).lower() != "content-type"}

    lines = [
        "import io",
        "import os",
        "import requests",
        "",
        f'BASE_URL = os.getenv("BASE_URL", "{BASE_URL}")',
        "",
        f"def test_{safe_name(method)}_{safe_name(path)}_upload():",
        f"    url = {_url_expr(path, case)}",
        f"    headers = {render_value(headers)}",
        f"    files = {{{render_value(file_field)}: {file_tuple}}}",
    ]
    if params:
        lines.append(f"    params = {render_value(params)}")
        lines.append(f"    response = requests.{method_lower}(url, params=params, files=files, headers=headers or None, timeout=30)")
    else:
        lines.append(f"    response = requests.{method_lower}(url, files=files, headers=headers or None, timeout=30)")
    lines.extend([
        f"    assert response.status_code == {status}",
        "    # 上传/导入接口返回内容依赖服务端处理，优先保证脚本可执行，不强断言中文消息。",
        "",
    ])
    return "\n".join(lines)


def generate_special_endpoint_code(method: str, path: str, log_cases: List[Dict[str, Any]], code_info: Dict[str, Any]) -> str:
    kind = endpoint_kind(method, path)
    if kind == "download":
        return _download_code(method, path, log_cases, code_info)
    if kind == "upload":
        return _upload_code(method, path, log_cases, code_info)
    return ""
