import os
from collections import Counter
from typing import Any, Dict, List

from core.config import MODEL, SUMMARY_FILE, USE_OLLAMA


SUMMARY_FILE_PATH = SUMMARY_FILE


def set_summary_file(summary_file: str) -> None:
    global SUMMARY_FILE_PATH
    SUMMARY_FILE_PATH = summary_file


def classify_error(error_msg: str) -> str:
    if not error_msg:
        return ""

    msg = error_msg.lower()
    if "syntaxerror" in msg or "invalid syntax" in msg:
        return "SyntaxError"
    if "no tests ran" in msg:
        return "NoTestsGenerated"
    if "timeout" in msg:
        return "Timeout"
    if "connection" in msg or "max retries exceeded" in msg:
        return "ConnectionError"
    if "assert" in msg:
        return "AssertionError"
    if "import" in msg and "error" in msg:
        return "ImportError"
    return "OtherError"


def _rate(part: int, total: int) -> float:
    return round(part / total * 100, 2) if total else 0.0


def write_summary(rows: List[Dict[str, Any]], total_generate_time_s: float = None, total_run_time_s: float = None, sum_endpoint_generate_time_s: float = None) -> None:
    if not rows:
        os.makedirs(os.path.dirname(SUMMARY_FILE_PATH) or ".", exist_ok=True)
        with open(SUMMARY_FILE_PATH, "w", encoding="utf-8") as f:
            f.write("没有可统计的数据。\n")
        return

    total = len(rows)
    gen_success = sum(1 for r in rows if r["generate_success"])
    syntax_success = sum(1 for r in rows if r["syntax_success"])
    pytest_success = sum(1 for r in rows if r["pytest_success"])
    fix_retry = sum(1 for r in rows if r["fix_retry_used"])
    fallback_used = sum(1 for r in rows if r.get("fallback_used"))
    pytest_passed_cases = sum(int(r.get("pytest_passed_count", 0) or 0) for r in rows)
    pytest_failed_cases = sum(int(r.get("pytest_failed_count", 0) or 0) for r in rows)
    pytest_error_cases = sum(int(r.get("pytest_error_count", 0) or 0) for r in rows)
    pytest_skipped_cases = sum(int(r.get("pytest_skipped_count", 0) or 0) for r in rows)
    pytest_total_cases = pytest_passed_cases + pytest_failed_cases + pytest_error_cases + pytest_skipped_cases
    pytest_executable_cases = pytest_total_cases - pytest_error_cases
    script_executable_rate = _rate(pytest_executable_cases, pytest_total_cases)
    pytest_case_pass_rate = _rate(pytest_passed_cases, pytest_total_cases)
    total_normal_cases = sum(int(r.get("normal_case_count", 0) or 0) for r in rows)
    total_exception_cases = sum(int(r.get("exception_case_count", 0) or 0) for r in rows)
    total_executed_cases = total_normal_cases + total_exception_cases
    exception_case_rate = _rate(total_exception_cases, total_executed_cases)

    kb_counter = Counter(r.get("actual_knowledge_base", "") for r in rows)
    mode_counter = Counter(r.get("generation_mode", "") for r in rows)
    exception_mode_counter = Counter(r.get("exception_mode", "") for r in rows)

    log_hit = sum(1 for r in rows if r.get("log_case_count", 0) > 0)
    code_hit = sum(1 for r in rows if r.get("code_scan_matched"))
    times = [r["generate_time_s"] for r in rows if r.get("generate_time_s", 0) > 0]
    total_generate_time = round(total_generate_time_s, 2) if total_generate_time_s is not None else (round(sum(times), 2) if times else 0)
    endpoint_generate_time_sum = round(sum_endpoint_generate_time_s, 2) if sum_endpoint_generate_time_s is not None else (round(sum(times), 2) if times else 0)
    total_run_time = round(total_run_time_s, 2) if total_run_time_s is not None else 0

    summary = [
        "=== 接口测试脚本生成统计 ===",
        f"模型：{MODEL if USE_OLLAMA else 'template'}",
        f"接口总数：{total}",
        f"生成成功数：{gen_success}",
        f"生成成功率：{_rate(gen_success, total)}%",
        f"语法通过数：{syntax_success}",
        f"语法通过率：{_rate(syntax_success, total)}%",
        f"pytest通过接口数：{pytest_success}",
        f"pytest接口通过率：{_rate(pytest_success, total)}%",
        f"pytest用例通过数：{pytest_passed_cases}",
        f"pytest用例失败数：{pytest_failed_cases}",
        f"pytest用例错误数：{pytest_error_cases}",
        f"pytest用例跳过数：{pytest_skipped_cases}",
        f"脚本可执行用例数：{pytest_executable_cases}",
        f"脚本可执行率：{script_executable_rate}%",
        f"pytest用例通过率：{pytest_case_pass_rate}%",
        f"日志命中接口数：{log_hit}",
        f"代码扫描命中接口数：{code_hit}",
        f"生成代码后处理次数：{fix_retry}",
        f"触发兜底接口数：{fallback_used}",
        f"正常用例数：{total_normal_cases}",
        f"异常用例数：{total_exception_cases}",
        f"异常用例占比：{exception_case_rate}%",
        f"生成总耗时：{total_generate_time} 秒",
        f"接口生成耗时累计：{endpoint_generate_time_sum} 秒",
        f"本次运行总耗时：{total_run_time} 秒",
        f"平均生成耗时：{round(endpoint_generate_time_sum / len(times), 2) if times else 0} 秒",
        f"最长生成耗时：{round(max(times), 2) if times else 0} 秒",
        f"最短生成耗时：{round(min(times), 2) if times else 0} 秒",
        "",
        "实际命中来源统计：",
    ]

    for name, count in sorted(kb_counter.items()):
        summary.append(f"- {name or 'unknown'}：{count}")

    summary.append("")
    summary.append("执行模式：")
    for name, count in sorted(mode_counter.items()):
        summary.append(f"- {name or 'unknown'}：{count}")

    summary.append("")
    summary.append("异常用例模式：")
    for name, count in sorted(exception_mode_counter.items()):
        summary.append(f"- {name or 'unknown'}：{count}")

    summary_text = "\n".join(summary) + "\n"
    os.makedirs(os.path.dirname(SUMMARY_FILE_PATH) or ".", exist_ok=True)
    with open(SUMMARY_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(summary_text)
    print("\n" + summary_text)
