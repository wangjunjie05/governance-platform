"""单个接口生成流程模块。"""
import os
import time
from typing import Any, Dict, List

from core.config import MODEL, USE_OLLAMA, MAX_NORMAL_CASES_PER_API
from core.generators.code_postprocess import check_parametrize_args, has_pytest_test_function, post_process_generated_code
from core.generators.fallback_generator import generate_fallback_code
from core.parsers.swagger_parser import build_api_doc
from core.executors.validator import check_pytest, check_syntax
from core.reporting.case_reporter import load_case_rows, summarize_case_rows, dedupe_case_rows
from core.reporting.result_writer import classify_error
from core.utils.common import safe_name

from .config_validator import detect_data_source, get_knowledge_base, get_actual_knowledge_base
from .context_collector import collect_context, has_normal_case_rows
from .code_generator import (
    generate_code,
    try_fix_code_once,
    save_code,
    attach_rule_cases,
    ensure_success_baseline,
    attach_normal_baseline,
)


def generate_one_endpoint(
    idx: int,
    total: int,
    spec: Dict[str, Any],
    path: str,
    method: str,
    op: Dict[str, Any],
    log_map: Dict[str, List[Dict[str, Any]]],
    mode: str,
    out_dir: str,
    reports_dir: str,
    exception_mode: str,
    max_normal_cases: int = None,
    code_dir: str = None,
    code_include=None,
    code_exclude=None,
    base_url: str = None,
    default_headers: Dict[str, Any] = None,
    code_scan_cache: Dict[str, Dict[str, Any]] = None,
    governance_context: str = None,
) -> Dict[str, Any]:
    """生成单个接口的测试代码。"""
    from core.config import ENABLE_FIX_RETRY
    governance_context = governance_context or ""

    file_name = f"test_{safe_name(method)}_{safe_name(path)}.py"
    file_path = os.path.join(out_dir, file_name)
    pytest_report_name = file_name.replace(".py", ".txt")
    pytest_report_path = os.path.join(reports_dir, pytest_report_name)
    case_jsonl_path = os.path.join(reports_dir, file_name.replace(".py", ".jsonl"))

    generate_success = False
    syntax_success = False
    pytest_success = False
    fix_retry_used = False
    fallback_used = False
    fallback_reason = ""
    generate_time_s = 0.0
    code_length = 0
    error_msg = ""
    pytest_counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    case_rows = []
    actual_normal_case_count = 0
    actual_exception_case_count = 0

    log_cases, code_info, exception_cases = collect_context(
        spec, path, method, op, log_map, mode, exception_mode,
        code_dir=code_dir, code_include=code_include, code_exclude=code_exclude,
        default_headers=default_headers, code_scan_cache=code_scan_cache
    )
    data_source = detect_data_source(log_cases, code_info)
    knowledge_base = get_knowledge_base(mode, log_cases, code_info)
    actual_knowledge_base = get_actual_knowledge_base(mode, log_cases, code_info)

    try:
        api_doc = build_api_doc(spec, path, method, op)
        start = time.time()

        try:
            code = generate_code(api_doc, method, path, log_cases, code_info, exception_cases, governance_context=governance_context)
        except Exception as err:
            code = post_process_generated_code(generate_fallback_code(method, path, log_cases, code_info))
            fallback_used = True
            fallback_reason = f"Ollama 调用失败：{err}"
            error_msg = f"Ollama 调用失败，已使用模板兜底：{err}"

        code = attach_rule_cases(code, method, path, log_cases, code_info, exception_cases, exception_mode)
        code = ensure_success_baseline(code, method, path, log_cases, code_info, max_cases=(max_normal_cases or MAX_NORMAL_CASES_PER_API))

        generate_time_s = round(time.time() - start, 2)

        if not has_pytest_test_function(code):
            code = attach_rule_cases(generate_fallback_code(method, path, log_cases, code_info), method, path, log_cases, code_info, exception_cases, exception_mode)
            code = ensure_success_baseline(code, method, path, log_cases, code_info, max_cases=(max_normal_cases or MAX_NORMAL_CASES_PER_API))
            fallback_used = True
            fallback_reason = "生成代码未包含测试函数"
            fix_retry_used = True

        code_length = len(code)
        save_code(file_path, code, base_url)
        generate_success = True

        syntax_success, syntax_err = check_syntax(file_path)
        if not syntax_success and ENABLE_FIX_RETRY and USE_OLLAMA:
            try:
                fixed_code, fix_retry_used = try_fix_code_once(code, syntax_err)
                if not has_pytest_test_function(fixed_code):
                    fixed_code = attach_rule_cases(generate_fallback_code(method, path, log_cases, code_info), method, path, log_cases, code_info, exception_cases, exception_mode)
                    fixed_code = ensure_success_baseline(fixed_code, method, path, log_cases, code_info, max_cases=(max_normal_cases or MAX_NORMAL_CASES_PER_API))
                    fix_retry_used = True
                else:
                    fixed_code = attach_rule_cases(fixed_code, method, path, log_cases, code_info, exception_cases, exception_mode)
                    fixed_code = ensure_success_baseline(fixed_code, method, path, log_cases, code_info, max_cases=(max_normal_cases or MAX_NORMAL_CASES_PER_API))
                save_code(file_path, fixed_code, base_url)
                code = fixed_code
                code_length = len(code)
                syntax_success, syntax_err = check_syntax(file_path)
            except Exception as fix_err:
                syntax_err = f"{syntax_err} | 自动修复失败：{fix_err}"

        if not syntax_success:
            fallback_code = attach_rule_cases(generate_fallback_code(method, path, log_cases, code_info), method, path, log_cases, code_info, exception_cases, exception_mode)
            fallback_code = ensure_success_baseline(fallback_code, method, path, log_cases, code_info, max_cases=(max_normal_cases or MAX_NORMAL_CASES_PER_API))
            save_code(file_path, fallback_code, base_url)
            code = fallback_code
            code_length = len(code)
            fallback_used = True
            fallback_reason = fallback_reason or f"语法错误且修复失败：{syntax_err}"
            fix_retry_used = True
            syntax_success, syntax_err = check_syntax(file_path)

        if not syntax_success:
            error_msg = syntax_err
        else:
            parametrize_ok, parametrize_err = check_parametrize_args(code)
            if not parametrize_ok:
                error_msg = parametrize_err
            else:
                pytest_success, pytest_err, pytest_counts = check_pytest(file_path, pytest_report_path, case_jsonl_path, base_url=base_url, replay_headers=default_headers)

                current_case_rows = dedupe_case_rows(load_case_rows(case_jsonl_path))
                if not has_normal_case_rows(current_case_rows):
                    code = attach_normal_baseline(
                        code,
                        method,
                        path,
                        log_cases,
                        code_info,
                        max_cases=(max_normal_cases or MAX_NORMAL_CASES_PER_API),
                        force=True,
                    )
                    save_code(file_path, code, base_url)
                    code_length = len(code)
                    fix_retry_used = True
                    syntax_success, syntax_err = check_syntax(file_path)
                    if syntax_success:
                        pytest_success, pytest_err, pytest_counts = check_pytest(file_path, pytest_report_path, case_jsonl_path, base_url=base_url, replay_headers=default_headers)

                if int(pytest_counts.get("errors", 0) or 0) > 0:
                    repaired_code = attach_rule_cases(
                        generate_fallback_code(method, path, log_cases, code_info),
                        method,
                        path,
                        log_cases,
                        code_info,
                        exception_cases,
                        exception_mode,
                    )
                    repaired_code = attach_normal_baseline(
                        repaired_code,
                        method,
                        path,
                        log_cases,
                        code_info,
                        max_cases=(max_normal_cases or MAX_NORMAL_CASES_PER_API),
                        force=True,
                    )
                    save_code(file_path, repaired_code, base_url)
                    code = repaired_code
                    code_length = len(code)
                    fix_retry_used = True
                    syntax_success, syntax_err = check_syntax(file_path)
                    if syntax_success:
                        pytest_success, pytest_err, pytest_counts = check_pytest(file_path, pytest_report_path, case_jsonl_path, base_url=base_url, replay_headers=default_headers)

                if not pytest_success and log_cases:
                    repaired_code = attach_rule_cases(generate_fallback_code(method, path, log_cases, code_info), method, path, log_cases, code_info, exception_cases, exception_mode)
                    repaired_code = ensure_success_baseline(repaired_code, method, path, log_cases, code_info, max_cases=(max_normal_cases or MAX_NORMAL_CASES_PER_API))
                    save_code(file_path, repaired_code, base_url)
                    code = repaired_code
                    code_length = len(code)
                    fix_retry_used = True
                    syntax_success, syntax_err = check_syntax(file_path)
                    if syntax_success:
                        pytest_success, pytest_err, pytest_counts = check_pytest(file_path, pytest_report_path, case_jsonl_path, base_url=base_url, replay_headers=default_headers)

                if not pytest_success and not error_msg:
                    error_msg = pytest_err

        case_rows = dedupe_case_rows(load_case_rows(case_jsonl_path))
        for item in case_rows:
            item["file_name"] = file_name

        collected_summary = summarize_case_rows(case_rows)
        missing_error_count = max(
            0,
            int(pytest_counts.get("errors", 0) or 0) - int(collected_summary.get("errors", 0) or 0),
        )
        for err_idx in range(missing_error_count):
            case_rows.append({
                "file_name": file_name,
                "test_name": f"pytest_error_{err_idx + 1}",
                "case_type": "异常",
                "result": "error",
                "method": method,
                "url": path,
                "params": {},
                "request_body": {},
                "response_status": "",
                "response_body": "",
                "duration_s": "",
                "error_msg": pytest_err if 'pytest_err' in locals() else error_msg,
            })

        case_rows = dedupe_case_rows(case_rows)
        case_summary = summarize_case_rows(case_rows)
        if case_rows:
            pytest_counts = {
                "passed": case_summary["passed"],
                "failed": case_summary["failed"],
                "errors": case_summary["errors"],
                "skipped": case_summary["skipped"],
            }
            actual_normal_case_count = case_summary["normal_case_count"]
            actual_exception_case_count = case_summary["exception_case_count"]
    except Exception as err:
        error_msg = str(err)

    total_case_count = (
        int(pytest_counts.get("passed", 0) or 0)
        + int(pytest_counts.get("failed", 0) or 0)
        + int(pytest_counts.get("errors", 0) or 0)
        + int(pytest_counts.get("skipped", 0) or 0)
    )
    executable_case_count = total_case_count - int(pytest_counts.get("errors", 0) or 0)
    script_executable_rate = round(executable_case_count / total_case_count * 100, 2) if total_case_count else 0.0
    pytest_case_pass_rate = round(int(pytest_counts.get("passed", 0) or 0) / total_case_count * 100, 2) if total_case_count else 0.0

    error_type = classify_error(error_msg)
    row = {
        "_idx": idx,
        "method": method,
        "path": path,
        "file_name": file_name,
        "model": MODEL if USE_OLLAMA else "template",
        "generate_time_s": generate_time_s,
        "generate_success": generate_success,
        "syntax_success": syntax_success,
        "pytest_success": pytest_success,
        "fix_retry_used": fix_retry_used,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "code_length": code_length,
        "data_source": data_source,
        "knowledge_base": knowledge_base,
        "actual_knowledge_base": actual_knowledge_base,
        "generation_mode": mode,
        "exception_mode": exception_mode,
        "log_case_count": len(log_cases),
        "code_scan_matched": code_info.get("matched", False),
        "normal_case_count": actual_normal_case_count,
        "exception_case_count": actual_exception_case_count,
        "exception_case_rate": _exception_rate(actual_normal_case_count, actual_exception_case_count),
        "pytest_passed_count": pytest_counts.get("passed", 0),
        "pytest_failed_count": pytest_counts.get("failed", 0),
        "pytest_error_count": pytest_counts.get("errors", 0),
        "pytest_skipped_count": pytest_counts.get("skipped", 0),
        "script_executable_rate": script_executable_rate,
        "pytest_case_pass_rate": pytest_case_pass_rate,
        "pytest_report_file": os.path.abspath(pytest_report_path),
        "pytest_case_jsonl_file": os.path.abspath(case_jsonl_path),
        "error_type": error_type,
        "error_msg": error_msg,
    }

    print(
        f"[{idx:03d}/{total:03d}] {method} {path} -> {file_name} | "
        f"kb={knowledge_base} | ex_mode={exception_mode} | logs={len(log_cases)} | "
        f"code={code_info.get('matched', False)} | syntax={syntax_success} | pytest={pytest_success} | "
        f"time={generate_time_s}s"
    )
    return row


def _exception_rate(normal_count: int, exception_count: int) -> float:
    """计算异常用例占比。"""
    total = normal_count + exception_count
    return round(exception_count / total * 100, 2) if total else 0.0
