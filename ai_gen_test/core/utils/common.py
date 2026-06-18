import re


def safe_name(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_") or "api"


def build_key(method: str, path: str) -> str:
    return f"{method.upper()} {path}"
