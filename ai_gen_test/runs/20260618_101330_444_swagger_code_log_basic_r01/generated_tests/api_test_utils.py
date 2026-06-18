
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
