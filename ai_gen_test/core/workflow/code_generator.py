"""代码生成核心逻辑模块。"""
import os
import re
from typing import Any, Dict, List, Tuple

from core.config import BASE_URL, MAX_NORMAL_CASES_PER_API, USE_OLLAMA
from core.generators.code_postprocess import has_pytest_test_function, post_process_generated_code
from core.generators.exception_test_generator import build_exception_test_code, build_normal_test_code, _choose_success_case
from core.generators.fallback_generator import generate_fallback_code
from core.generators.llm_client import call_ollama
from core.generators.prompt_builder import build_fix_prompt, build_prompt
from core.generators.special_endpoint_generator import generate_special_endpoint_code, is_special_endpoint


def generate_code(api_doc: str, method: str, path: str, log_cases: List[Dict[str, Any]], code_info: Dict[str, Any], exception_cases: List[Dict[str, Any]], governance_context: str = None) -> str:
    """生成测试代码。"""
    special_code = generate_special_endpoint_code(method, path, log_cases, code_info)
    if special_code:
        return post_process_generated_code(special_code)

    prompt = build_prompt(api_doc, method, path, log_cases, code_info, exception_cases, governance_context=governance_context)

    if USE_OLLAMA:
        raw_code = call_ollama(prompt)
        return post_process_generated_code(raw_code)

    return post_process_generated_code(generate_fallback_code(method, path, log_cases, code_info))


def try_fix_code_once(code: str, error_msg: str) -> Tuple[str, bool]:
    """尝试修复代码一次。"""
    fixed_code = call_ollama(build_fix_prompt(code, error_msg))
    return post_process_generated_code(fixed_code), True


def _apply_base_url_default(code: str, base_url: str = None) -> str:
    """把生成脚本里的 BASE_URL 默认值改成本次运行实际使用的地址。"""
    if not base_url:
        return code
    base_url = str(base_url).rstrip("/")
    pattern = r'os\.getenv\(\s*["\']BASE_URL["\']\s*,\s*["\'][^"\']*["\']\s*\)'
    return re.sub(pattern, f'os.getenv("BASE_URL", "{base_url}")', code)


def save_code(file_path: str, code: str, base_url: str = None) -> None:
    """保存代码到文件。"""
    code = _apply_base_url_default(code, base_url)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(code)


def strip_rule_cases(code: str) -> str:
    """移除规则用例代码段，防止重复追加。"""
    code = re.sub(
        r"\n# 正常基线用例：每个接口至少保留一条，[\s\S]*?(?=\n# 以下异常用例|\ndef\s+test_|\n@pytest\.|\Z)",
        "\n",
        code,
    )
    code = re.sub(
        r"\n# 以下异常用例由程序根据 DTO 校验注解和接口参数规则自动扩展。[\s\S]*?(?=\ndef\s+test_|\n@pytest\.|\Z)",
        "\n",
        code,
    )
    return code.strip() + "\n"


def _success_log_case(log_cases: List[Dict[str, Any]], code_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """选择一个成功的日志用例。"""
    return _choose_success_case(log_cases, code_info or {})


def _code_has_success_case(code: str, success_case: Dict[str, Any]) -> bool:
    """判断当前测试代码是否已经覆盖真实成功日志。"""
    if not success_case:
        return False

    status = str(success_case.get("http_status") or "")
    if not status:
        return False

    actual_path = str(success_case.get("path") or "")
    template_path = str(success_case.get("path_template") or "")

    path_hit = False
    if actual_path and actual_path in code:
        path_hit = True
    if template_path and template_path in code:
        path_hit = True

    if not path_hit and template_path and "{" in template_path:
        parts = [part for part in re.split(r"\{[^/]+\}", template_path) if part]
        if parts and all(part in code for part in parts):
            path_hit = True

    status_patterns = [
        rf"status_code\s*==\s*{re.escape(status)}",
        rf"expected_status(?:_code)?\s*=\s*{re.escape(status)}",
        rf"[,\(]\s*{re.escape(status)}\s*[,\)]",
        rf":\s*{re.escape(status)}\b",
    ]
    status_hit = any(re.search(pattern, code) for pattern in status_patterns)
    return path_hit and status_hit


def _code_has_success_for_path(code: str, path: str, status: int = 200) -> bool:
    """判断代码中是否包含指定路径的成功用例。"""
    path_hit = False
    if path and path in code:
        path_hit = True
    if not path_hit and path and "{" in path:
        parts = [part for part in re.split(r"\{[^/]+\}", path) if part]
        if parts and all(part in code for part in parts):
            path_hit = True

    status_text = str(status)
    status_patterns = [
        rf"status_code\s*==\s*{re.escape(status_text)}",
        rf"expected_status(?:_code)?\s*=\s*{re.escape(status_text)}",
        rf"[,\(]\s*{re.escape(status_text)}\s*[,\)]",
        rf":\s*{re.escape(status_text)}\b",
    ]
    return path_hit and any(re.search(pattern, code) for pattern in status_patterns)


def _can_infer_success_from_code(code_info: Dict[str, Any]) -> bool:
    """判断是否能从代码信息推断成功场景。"""
    if not code_info or not code_info.get("matched"):
        return False
    if 200 in (code_info.get("business_codes") or []) or 200 in (code_info.get("status_codes") or []):
        return True
    snippet = code_info.get("logic_snippet") or ""
    return "Result.ok" in snippet or "success" in snippet.lower()


def ensure_success_baseline(
    code: str,
    method: str,
    path: str,
    log_cases: List[Dict[str, Any]],
    code_info: Dict[str, Any],
    max_cases: int = None,
) -> str:
    """保证正常基线用例。"""
    if "AUTO_NORMAL_CASES" in code:
        return code

    success_count = _count_success_log_cases(log_cases)
    success_case = _success_log_case(log_cases, code_info)

    if success_count > 1:
        return attach_normal_baseline(code, method, path, log_cases, code_info, max_cases=max_cases)

    if success_case and _code_has_success_case(code, success_case):
        return code

    if not success_case and _code_has_success_for_path(code, path, 200):
        return code

    return attach_normal_baseline(code, method, path, log_cases, code_info, max_cases=max_cases)


def _count_success_log_cases(log_cases: List[Dict[str, Any]]) -> int:
    """统计成功日志用例数量。"""
    count = 0
    for case in log_cases or []:
        try:
            if int(case.get("http_status") or 0) < 400:
                count += 1
        except Exception:
            pass
    return count


def attach_rule_cases(code: str, method: str, path: str, log_cases: List[Dict[str, Any]], code_info: Dict[str, Any], exception_cases: List[Dict[str, Any]], exception_mode: str) -> str:
    """追加规则异常用例。"""
    code = strip_rule_cases(code)
    parts = [code.rstrip()]

    if exception_mode in {"basic", "full"} and exception_cases:
        exception_code = build_exception_test_code(method, path, log_cases, code_info, exception_cases)
        if exception_code:
            parts.append(exception_code.rstrip())

    return post_process_generated_code("\n\n".join(p for p in parts if p).strip() + "\n")


def attach_normal_baseline(
    code: str,
    method: str,
    path: str,
    log_cases: List[Dict[str, Any]],
    code_info: Dict[str, Any],
    max_cases: int = None,
    force: bool = False,
) -> str:
    """补充正常基线用例。"""
    if not force:
        success_case = _success_log_case(log_cases, code_info)
        if success_case and _code_has_success_case(code, success_case):
            return code
        if not success_case and _code_has_success_for_path(code, path, 200):
            return code

    normal_code = build_normal_test_code(method, path, log_cases, code_info, max_cases=max_cases)
    if not normal_code:
        return code
    return post_process_generated_code("\n\n".join([code.rstrip(), normal_code.rstrip()]).strip() + "\n")
