"""配置验证和参数标准化模块。"""
from typing import Any, Dict, List, Tuple

from core.config import (
    API_PATH_KEYWORDS,
    API_PATH_PREFIXES,
    CODE_EXCLUDE_KEYWORDS,
    CODE_INCLUDE_KEYWORDS,
    EXCEPTION_MODE,
    GENERATION_MODE,
    VALID_EXCEPTION_MODES,
    VALID_GENERATION_MODES,
)


def _split_csv(value) -> List[str]:
    """将CSV格式字符串或列表转换为列表。"""
    if not value:
        return []
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    return [str(x).strip() for x in value if str(x).strip()]


def normalize_generation_mode(mode: str = None) -> str:
    """标准化生成模式。"""
    mode = (mode or GENERATION_MODE).strip().lower()
    if mode not in VALID_GENERATION_MODES:
        raise ValueError(f"mode 只能是 {sorted(VALID_GENERATION_MODES)}，当前值：{mode}")
    return mode


def normalize_exception_mode(exception_mode: str = None) -> str:
    """标准化异常用例模式。"""
    mode = (exception_mode or EXCEPTION_MODE).strip().lower()
    if mode not in VALID_EXCEPTION_MODES:
        raise ValueError(f"exception-mode 只能是 {sorted(VALID_EXCEPTION_MODES)}，当前值：{mode}")
    return mode


def normalize_path_filters(api_prefixes=None, api_keywords=None) -> Tuple[List[str], List[str]]:
    """标准化路径过滤参数。"""
    return _split_csv(api_prefixes or API_PATH_PREFIXES), _split_csv(api_keywords or API_PATH_KEYWORDS)


def normalize_code_filters(code_include=None, code_exclude=None) -> Tuple[List[str], List[str]]:
    """标准化代码扫描过滤参数。"""
    includes = _split_csv(code_include or CODE_INCLUDE_KEYWORDS)
    excludes = _split_csv(code_exclude or CODE_EXCLUDE_KEYWORDS)
    return includes, excludes


def endpoint_allowed(path: str, api_prefixes=None, api_keywords=None) -> bool:
    """判断接口是否允许生成。"""
    prefixes, keywords = normalize_path_filters(api_prefixes, api_keywords)
    if prefixes and not any(path.startswith(prefix) for prefix in prefixes):
        return False
    if keywords and not any(keyword in path for keyword in keywords):
        return False
    return True


def filter_endpoints(endpoints, api_prefixes=None, api_keywords=None):
    """过滤接口列表。"""
    return [(p, m, op) for p, m, op in endpoints if endpoint_allowed(p, api_prefixes, api_keywords)]


def get_requested_knowledge_base(mode: str) -> str:
    """获取请求的知识库类型。"""
    if mode == "swagger":
        return "swagger"
    if mode == "swagger_code":
        return "swagger+code"
    if mode == "swagger_code_log":
        return "swagger+code+log"
    return mode


def get_actual_knowledge_base(mode: str, log_cases: List[Dict[str, Any]], code_info: Dict[str, Any]) -> str:
    """获取实际使用的知识库类型。"""
    parts = ["swagger"]
    if mode in {"swagger_code", "swagger_code_log"} and code_info.get("matched"):
        parts.append("code")
    if mode == "swagger_code_log" and log_cases:
        parts.append("log")
    return "+".join(parts)


def get_knowledge_base(mode: str, log_cases: List[Dict[str, Any]], code_info: Dict[str, Any]) -> str:
    """兼容旧字段：返回期望使用的知识库。"""
    return get_requested_knowledge_base(mode)


def detect_data_source(log_cases: List[Dict[str, Any]], code_info: Dict[str, Any]) -> str:
    """检测实际数据源类型。"""
    if log_cases and code_info.get("matched"):
        return "log+code"
    if log_cases:
        return "log"
    if code_info.get("matched"):
        return "code"
    return "swagger_only"
