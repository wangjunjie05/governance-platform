from typing import Any, Dict, List


def _rule_value(rule: Dict[str, Any], key: str, default: Any = None) -> Any:
    value = rule.get(key, default)
    if value in (None, ""):
        return default
    return value


def _invalid_type_value(field_type: str) -> Any:
    t = (field_type or "").lower()
    if any(x in t for x in ["integer", "int", "long", "bigdecimal", "double", "float"]):
        return "abc"
    if "boolean" in t:
        return "not_boolean"
    return 12345



def _should_add_invalid_type(field_type: str) -> bool:
    """是否适合生成类型错误用例。

    Java/Jackson 对 String 字段比较宽松，数字 12345 可能会被自动转成 "12345"，
    这种用例经常不会触发 400，反而拉低结果可信度，所以 String 类型不生成类型错误。
    """
    t = (field_type or "").lower()
    if not t:
        return False
    if "string" in t:
        return False
    return any(x in t for x in ["integer", "int", "long", "bigdecimal", "double", "float", "boolean", "enum"])

def _add_unique(cases: List[Dict[str, Any]], seen: set, case: Dict[str, Any]) -> None:
    key = (
        case.get("case_type"),
        case.get("field"),
        case.get("location"),
        case.get("source"),
        str(case.get("value")),
        case.get("message"),
        case.get("condition"),
    )
    if key in seen:
        return
    seen.add(key)
    cases.append(case)


def _build_all_exception_cases(method: str, path: str, log_cases: List[Dict[str, Any]], code_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    seen = set()

    for rule in code_info.get("validation_rules", []) or []:
        field = rule.get("field")
        if not field:
            continue

        field_type = rule.get("type", "")
        ann = rule.get("annotation", "")
        location = rule.get("location", "body")
        message = rule.get("message", "")

        base = {
            "source": "validation",
            "location": location,
            "field": field,
            "java_type": field_type,
            "annotation": ann,
            "expected_http_status": 400,
            "message": message,
        }

        if ann in {"NotNull", "NotBlank", "NotEmpty"}:
            _add_unique(cases, seen, {**base, "case_type": "missing_param", "value": "<remove this field>", "description": f"缺少必填参数 {field}"})
        if ann in {"NotBlank", "NotEmpty"}:
            _add_unique(cases, seen, {**base, "case_type": "blank_param", "value": "", "description": f"参数 {field} 为空字符串"})
        if ann == "NotNull":
            _add_unique(cases, seen, {**base, "case_type": "null_param", "value": None, "description": f"参数 {field} 为 null"})

        if ann == "Size":
            min_len = _rule_value(rule, "min")
            max_len = _rule_value(rule, "max")
            if min_len is not None:
                try:
                    _add_unique(cases, seen, {**base, "case_type": "size_too_short", "value": "a" * max(int(min_len) - 1, 0), "description": f"参数 {field} 长度小于最小值"})
                except Exception:
                    pass
            if max_len is not None:
                try:
                    _add_unique(cases, seen, {**base, "case_type": "size_too_long", "value": "a" * (int(max_len) + 1), "description": f"参数 {field} 长度超过最大值"})
                except Exception:
                    pass

        if ann in {"Min", "DecimalMin"}:
            min_value = _rule_value(rule, "value")
            if min_value is not None:
                try:
                    value = float(min_value) - 1
                    if str(min_value).isdigit():
                        value = int(float(min_value)) - 1
                    _add_unique(cases, seen, {**base, "case_type": "below_min", "value": value, "description": f"参数 {field} 小于最小值"})
                except Exception:
                    pass

        if ann in {"Max", "DecimalMax"}:
            max_value = _rule_value(rule, "value")
            if max_value is not None:
                try:
                    value = float(max_value) + 1
                    if str(max_value).isdigit():
                        value = int(float(max_value)) + 1
                    _add_unique(cases, seen, {**base, "case_type": "above_max", "value": value, "description": f"参数 {field} 大于最大值"})
                except Exception:
                    pass

        if ann == "Pattern":
            _add_unique(cases, seen, {**base, "case_type": "invalid_pattern", "value": "INVALID_VALUE", "description": f"参数 {field} 不符合正则"})
        if ann == "Email":
            _add_unique(cases, seen, {**base, "case_type": "invalid_email", "value": "invalid_email", "description": f"参数 {field} 邮箱格式错误"})
        if ann == "TypeHint" and _should_add_invalid_type(field_type):
            _add_unique(cases, seen, {**base, "case_type": "invalid_type", "value": _invalid_type_value(field_type), "description": f"参数 {field} 类型错误"})

        # 类型错误只针对数字、布尔、枚举等严格类型生成。
        # String 字段在 Java/Jackson 中可能自动把数字转成字符串，不能稳定触发异常。
        if ann != "TypeHint" and _should_add_invalid_type(field_type):
            _add_unique(cases, seen, {**base, "case_type": "invalid_type", "value": _invalid_type_value(field_type), "description": f"参数 {field} 类型错误"})

    for idx, msg in enumerate(code_info.get("exception_messages", []) or [], 1):
        _add_unique(cases, seen, {
            "source": "business_branch",
            "case_type": "business_exception",
            "location": "business_logic",
            "field": "",
            "expected_http_status": 400,
            "message": msg,
            "description": f"业务异常分支：{msg}",
        })

    for hint in code_info.get("enum_or_constant_hints", []) or []:
        _add_unique(cases, seen, {
            "source": "code_condition",
            "case_type": "condition_branch",
            "location": "business_logic",
            "field": "",
            "expected_http_status": 400,
            "condition": hint,
            "description": f"代码条件分支：{hint}",
        })

    return cases


def _basic_key(case: Dict[str, Any]) -> str:
    """basic 模式按异常类别收敛。

    同一个接口内每类异常只保留一个代表场景，避免 basic 模式膨胀成 full。
    例如：必填、长度、范围、类型、格式、业务分支、代码条件各保留 1 条。
    """
    case_type = case.get("case_type", "")
    if case_type in {"missing_param", "blank_param", "null_param"}:
        return "required"
    if case_type in {"size_too_short", "size_too_long"}:
        return "size"
    if case_type in {"below_min", "above_max"}:
        return "range"
    if case_type in {"invalid_pattern", "invalid_email"}:
        return "format"
    if case_type == "invalid_type":
        return "type"
    if case_type == "business_exception":
        return "business"
    if case_type == "condition_branch":
        return "condition"
    return case_type or "other"

def _select_basic_cases(cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    priority = {
        "missing_param": 10,
        "blank_param": 20,
        "null_param": 30,
        "size_too_short": 40,
        "size_too_long": 41,
        "below_min": 50,
        "above_max": 51,
        "invalid_type": 60,
        "invalid_pattern": 70,
        "invalid_email": 71,
        "business_exception": 80,
        "condition_branch": 90,
    }
    selected: Dict[str, Dict[str, Any]] = {}
    for case in cases:
        key = _basic_key(case)
        old = selected.get(key)
        if old is None or priority.get(case.get("case_type"), 999) < priority.get(old.get("case_type"), 999):
            selected[key] = case
    return list(selected.values())


def build_exception_cases(method: str, path: str, log_cases: List[Dict[str, Any]], code_info: Dict[str, Any], exception_mode: str = "basic") -> List[Dict[str, Any]]:
    """生成异常场景清单。

    exception_mode:
    - ai: 只给 AI 提示，不强制程序生成执行用例；为避免 Prompt 过长，使用 basic 清单。
    - basic: 每类异常保留代表场景，并由程序生成执行用例。
    - full: 识别到的异常场景全部由程序生成执行用例。
    """
    mode = (exception_mode or "basic").strip().lower()
    all_cases = _build_all_exception_cases(method, path, log_cases, code_info)
    if mode == "full":
        return all_cases
    return _select_basic_cases(all_cases)


def count_normal_cases(log_cases: List[Dict[str, Any]]) -> int:
    return len(log_cases) if log_cases else 1


def exception_rate(normal_case_count: int, exception_case_count: int) -> float:
    total = normal_case_count + exception_case_count
    return round(exception_case_count / total * 100, 2) if total else 0.0
