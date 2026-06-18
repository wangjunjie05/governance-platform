"""主运行流程模块。"""
import os
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Tuple

from core.config import (
    BASE_URL,
    CODE_DIR,
    GENERATE_WORKERS,
    LOG_FILE,
    MAX_NORMAL_CASES_PER_API,
    MODEL,
    RUNS_DIR,
    USE_OLLAMA,
)
from core.parsers.log_parser import extract_replay_headers_from_logs, infer_base_url_from_logs, load_api_logs
from core.parsers.swagger_parser import extract_endpoints, load_swagger
from core.executors.pytest_case_plugin import write_conftest
from core.reporting.case_reporter import load_case_rows, dedupe_case_rows, write_run_report_xlsx
from core.reporting.result_writer import write_summary, set_summary_file
from core.analyzers.exception_case_generator import exception_rate

from .config_validator import (
    normalize_generation_mode,
    normalize_exception_mode,
    normalize_code_filters,
    normalize_path_filters,
    filter_endpoints,
)
from .endpoint_generator import generate_one_endpoint


def print_startup_info(endpoints: List, log_map: Dict[str, List[Dict[str, Any]]], mode: str, exception_mode: str, code_dir: str, log_file: str, base_url: str = None, api_prefixes=None, api_keywords=None, code_include=None, code_exclude=None) -> None:
    """打印启动信息。"""
    from .config_validator import _split_csv

    print("\n========== 接口测试脚本生成 ==========")
    print(f"Swagger接口数：{len(endpoints)}")
    print(f"日志原始接口数：{len(log_map)}")
    if mode == "swagger_code_log":
        from core.parsers.log_parser import find_log_cases_for_endpoint
        matched_log_count = sum(1 for p, m, _ in endpoints if find_log_cases_for_endpoint(log_map, m, p))
        print(f"Swagger接口日志命中数：{matched_log_count}")
    print(f"生成模式：{mode}")
    print(f"异常用例模式：{exception_mode}")
    abs_code_dir = os.path.abspath(code_dir) if code_dir else ""
    print(f"代码目录：{abs_code_dir}")
    if mode in {"swagger_code", "swagger_code_log"} and (not code_dir or not os.path.isdir(code_dir)):
        print("代码目录不存在或未配置，已跳过代码扫描，仅使用 Swagger / 日志 / governance_context。")
    print(f"日志文件：{os.path.abspath(log_file)}")
    print(f"测试BASE_URL：{base_url or BASE_URL}")
    if _split_csv(api_prefixes):
        print(f"接口路径前缀过滤：{','.join(_split_csv(api_prefixes))}")
    if _split_csv(api_keywords):
        print(f"接口路径关键字过滤：{','.join(_split_csv(api_keywords))}")
    if _split_csv(code_include):
        print(f"代码扫描包含关键字：{','.join(_split_csv(code_include))}")
    if _split_csv(code_exclude):
        print(f"代码扫描排除目录：{','.join(_split_csv(code_exclude))}")
    print(f"使用Ollama：{USE_OLLAMA}")
    print("模式：swagger / swagger_code / swagger_code_log")
    print("====================================")

    if mode == "swagger_code_log" and log_map:
        print("\n日志接口：")
        for key in sorted(log_map.keys()):
            print(f"  {key}")
    print("\n开始生成...\n")


def make_run_dir(mode: str, exception_mode: str, repeat_index: int = None):
    """创建运行目录结构。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    suffix = f"_r{repeat_index:02d}" if repeat_index is not None else ""
    run_id = f"{timestamp}_{mode}_{exception_mode}{suffix}"
    run_dir = os.path.join(RUNS_DIR, run_id)
    tests_dir = os.path.join(run_dir, "generated_tests")
    reports_dir = os.path.join(run_dir, "pytest_reports")
    summary_file = os.path.join(run_dir, "summary.txt")
    run_report_xlsx = os.path.join(run_dir, "run_report.xlsx")
    os.makedirs(tests_dir, exist_ok=True)
    os.makedirs(reports_dir, exist_ok=True)
    return run_id, run_dir, tests_dir, reports_dir, summary_file, run_report_xlsx


def write_run_config(run_dir: str, run_info: Dict[str, Any]) -> None:
    """写入运行配置文件。"""
    import json
    config_path = os.path.join(run_dir, "run_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(run_info, f, ensure_ascii=False, indent=2)


def append_history(run_info: Dict[str, Any]) -> None:
    """追加运行记录到历史文件。"""
    import csv
    os.makedirs(RUNS_DIR, exist_ok=True)
    history_path = os.path.join(RUNS_DIR, "history.csv")
    fields = [
        ("run_id", "运行ID"),
        ("run_time", "运行时间"),
        ("mode", "生成模式"),
        ("exception_mode", "异常用例模式"),
        ("model", "模型"),
        ("use_ollama", "是否使用Ollama"),
        ("spec_path", "Swagger文件"),
        ("run_dir", "运行目录"),
        ("swagger_count", "Swagger接口数"),
        ("log_interface_count", "日志接口数"),
        ("generated_count", "生成接口数"),
        ("total_generate_time_s", "生成总耗时秒"),
        ("sum_endpoint_generate_time_s", "接口生成耗时累计秒"),
        ("total_run_time_s", "运行总耗时秒"),
        ("governance_context_used", "是否使用规范扫描上下文"),
        ("governance_context_chars", "规范扫描上下文字数"),
        ("governance_context_source", "规范扫描上下文来源"),
        ("generate_success_count", "生成成功数"),
        ("syntax_success_count", "语法通过数"),
        ("pytest_success_count", "pytest通过接口数"),
        ("fix_retry_count", "生成代码后处理次数"),
        ("pytest_passed_case_count", "pytest用例通过数"),
        ("pytest_failed_case_count", "pytest用例失败数"),
        ("pytest_error_case_count", "pytest用例错误数"),
        ("pytest_skipped_case_count", "pytest用例跳过数"),
        ("pytest_total_case_count", "pytest用例总数"),
        ("pytest_executable_case_count", "脚本可执行用例数"),
        ("script_executable_rate", "脚本可执行率"),
        ("pytest_case_pass_rate", "pytest用例通过率"),
        ("total_normal_case_count", "正常用例数"),
        ("total_exception_case_count", "异常用例数"),
        ("overall_exception_case_rate", "异常用例占比"),
        ("log_hit_count", "日志命中接口数"),
        ("code_hit_count", "代码扫描命中接口数"),
        ("generate_success_rate", "生成成功率"),
        ("syntax_success_rate", "语法通过率"),
        ("pytest_success_rate", "pytest接口通过率"),
    ]
    exists = os.path.exists(history_path)
    with open(history_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow([title for _, title in fields])
        writer.writerow([run_info.get(key, "") for key, _ in fields])




def resolve_governance_context(value: str, max_chars: int = 6000) -> Tuple[str, Dict[str, Any]]:
    """解析接口规范扫描补充信息。

    config/CLI 传入的 governance_context 通常是文件路径。这里统一解析为
    真正追加到 Prompt 的文本，并返回可写入 run_config.json 的追溯信息。
    """
    raw = str(value or "").strip()
    meta = {
        "governance_context": raw,
        "governance_context_used": False,
        "governance_context_chars": 0,
        "governance_context_source": "empty",
    }
    if not raw:
        return "", meta

    text = raw
    source = "text"
    # 支持 Windows 路径。Path.exists 在当前运行环境无法访问的绝对路径会返回 False，
    # 这种情况不阻断主流程，只记录 missing_file。
    candidate = Path(raw)
    if candidate.exists() and candidate.is_file():
        try:
            text = candidate.read_text(encoding="utf-8", errors="ignore")
            source = "file"
        except Exception as err:
            print(f"警告：governance_context 文件读取失败，已忽略：{raw}，原因：{err}")
            meta["governance_context_source"] = "missing_file"
            return "", meta
    elif any(sep in raw for sep in ("/", "\\")) or raw.lower().endswith(".txt"):
        print(f"警告：governance_context 文件不存在，已忽略：{raw}")
        meta["governance_context_source"] = "missing_file"
        return "", meta

    text = str(text or "").strip()
    if not text:
        meta["governance_context_source"] = source
        return "", meta

    original_len = len(text)
    if original_len > max_chars:
        text = text[:max_chars] + f"\n...（接口规范扫描补充信息已截断，原始长度 {original_len} 字符）"

    meta.update({
        "governance_context_used": True,
        "governance_context_chars": len(text),
        "governance_context_source": source,
    })
    return text, meta

def run_once(spec_path: str, mode: str = None, exception_mode: str = None, repeat_index: int = None, repeat_total: int = None, max_normal_cases_per_api: int = None, code_dir: str = None, log_file: str = None, api_prefixes=None, api_keywords=None, code_include=None, code_exclude=None, base_url: str = None, governance_context: str = None) -> Dict[str, Any]:
    """执行单次运行。"""
    run_start = time.time()
    mode = normalize_generation_mode(mode)
    exception_mode = normalize_exception_mode(exception_mode)
    max_normal_cases = max_normal_cases_per_api or MAX_NORMAL_CASES_PER_API
    code_dir = code_dir or CODE_DIR
    log_file = log_file or LOG_FILE
    code_include, code_exclude = normalize_code_filters(code_include, code_exclude)
    api_prefixes, api_keywords = normalize_path_filters(api_prefixes, api_keywords)
    governance_context_text, governance_context_meta = resolve_governance_context(governance_context or "")

    spec = load_swagger(spec_path)
    all_endpoints = extract_endpoints(spec)
    endpoints = filter_endpoints(all_endpoints, api_prefixes, api_keywords)
    if not all_endpoints:
        raise RuntimeError("未解析到接口，请检查 Swagger 文件。")
    if not endpoints:
        raise RuntimeError("接口过滤后没有可生成的接口，请检查 --api-prefix / --api-keyword 设置。")

    log_map = load_api_logs(log_file) if mode == "swagger_code_log" else {}
    effective_base_url = (base_url or os.getenv("BASE_URL") or infer_base_url_from_logs(log_map) or BASE_URL).rstrip("/")
    default_headers = extract_replay_headers_from_logs(log_map) if mode == "swagger_code_log" else {}
    run_id, run_dir, tests_dir, reports_dir, summary_file, run_report_xlsx = make_run_dir(mode, exception_mode, repeat_index=repeat_index)
    write_conftest(tests_dir)
    set_summary_file(summary_file)

    if repeat_total and repeat_total > 1:
        print(f"\n========== 第 {repeat_index}/{repeat_total} 轮 ==========")

    print_startup_info(endpoints, log_map, mode, exception_mode, code_dir, log_file, effective_base_url, api_prefixes, api_keywords, code_include, code_exclude)
    print(f"本次运行目录：{run_dir}")

    result_rows = []
    code_scan_cache: Dict[str, Dict[str, Any]] = {}
    workers = max(1, int(os.getenv("GENERATE_WORKERS", str(GENERATE_WORKERS)) or 1))
    workers = min(workers, len(endpoints)) if endpoints else 1

    def _run_endpoint(args):
        idx, path, method, op = args
        return generate_one_endpoint(
            idx,
            len(endpoints),
            spec,
            path,
            method,
            op,
            log_map,
            mode,
            tests_dir,
            reports_dir,
            exception_mode,
            max_normal_cases=max_normal_cases,
            code_dir=code_dir,
            code_include=code_include,
            code_exclude=code_exclude,
            base_url=effective_base_url,
            default_headers=default_headers,
            code_scan_cache=code_scan_cache,
            governance_context=governance_context_text,
        )

    endpoint_args = [(idx, path, method, op) for idx, (path, method, op) in enumerate(endpoints, 1)]
    generation_start = time.time()
    if workers == 1:
        result_rows = [_run_endpoint(args) for args in endpoint_args]
    else:
        print(f"并发生成线程数：{workers}")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_run_endpoint, args): args[0] for args in endpoint_args}
            for future in as_completed(futures):
                result_rows.append(future.result())
        result_rows.sort(key=lambda x: x.get("_idx", 0))
        for row in result_rows:
            row.pop("_idx", None)
    generation_wall_time_s = round(time.time() - generation_start, 2)

    all_case_rows = []
    for r in result_rows:
        report_jsonl = r.get("pytest_case_jsonl_file")
        rows = load_case_rows(report_jsonl)
        for item in rows:
            item["file_name"] = r.get("file_name", "")
        all_case_rows.extend(rows)
    all_case_rows = dedupe_case_rows(all_case_rows)
    write_run_report_xlsx(result_rows, all_case_rows, run_report_xlsx)

    sum_endpoint_generate_time_s = round(sum(float(r.get("generate_time_s", 0) or 0) for r in result_rows), 2)
    total_generate_time_s = generation_wall_time_s
    total_run_time_s = round(time.time() - run_start, 2)
    write_summary(
        result_rows,
        total_generate_time_s=total_generate_time_s,
        total_run_time_s=total_run_time_s,
        sum_endpoint_generate_time_s=sum_endpoint_generate_time_s,
    )

    total = len(result_rows)
    generate_success_count = sum(1 for r in result_rows if r.get("generate_success"))
    syntax_success_count = sum(1 for r in result_rows if r.get("syntax_success"))
    pytest_success_count = sum(1 for r in result_rows if r.get("pytest_success"))
    fix_retry_count = sum(1 for r in result_rows if r.get("fix_retry_used"))
    pytest_passed_case_count = sum(int(r.get("pytest_passed_count", 0) or 0) for r in result_rows)
    pytest_failed_case_count = sum(int(r.get("pytest_failed_count", 0) or 0) for r in result_rows)
    pytest_error_case_count = sum(int(r.get("pytest_error_count", 0) or 0) for r in result_rows)
    pytest_skipped_case_count = sum(int(r.get("pytest_skipped_count", 0) or 0) for r in result_rows)
    pytest_total_case_count = pytest_passed_case_count + pytest_failed_case_count + pytest_error_case_count + pytest_skipped_case_count
    pytest_executable_case_count = pytest_total_case_count - pytest_error_case_count
    script_executable_rate = round(pytest_executable_case_count / pytest_total_case_count * 100, 2) if pytest_total_case_count else 0.0
    pytest_case_pass_rate = round(pytest_passed_case_count / pytest_total_case_count * 100, 2) if pytest_total_case_count else 0.0
    total_exception_case_count = sum(int(r.get("exception_case_count", 0) or 0) for r in result_rows)
    total_normal_case_count = sum(int(r.get("normal_case_count", 0) or 0) for r in result_rows)
    overall_exception_case_rate = exception_rate(total_normal_case_count, total_exception_case_count)
    log_hit_count = sum(1 for r in result_rows if r.get("log_case_count", 0) > 0)
    code_hit_count = sum(1 for r in result_rows if r.get("code_scan_matched"))

    def rate(count: int) -> float:
        return round(count / total * 100, 2) if total else 0.0

    run_info = {
        "run_id": run_id,
        "run_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "exception_mode": exception_mode,
        "max_normal_cases_per_api": max_normal_cases,
        "model": MODEL if USE_OLLAMA else "template",
        "use_ollama": USE_OLLAMA,
        "spec_path": os.path.abspath(spec_path),
        "code_dir": os.path.abspath(code_dir),
        "log_file": os.path.abspath(log_file),
        "base_url": effective_base_url,
        "run_dir": os.path.abspath(run_dir),
        "generated_tests_dir": os.path.abspath(tests_dir),
        "pytest_reports_dir": os.path.abspath(reports_dir),
        "summary_file": os.path.abspath(summary_file),
        "run_report_xlsx": os.path.abspath(run_report_xlsx),
        "swagger_count": len(endpoints),
        "log_interface_count": len(log_map),
        "matched_log_interface_count": sum(1 for p, m, _ in endpoints if _has_log_case(log_map, m, p)),
        "generated_count": total,
        "total_generate_time_s": total_generate_time_s,
        "sum_endpoint_generate_time_s": sum_endpoint_generate_time_s,
        "total_run_time_s": total_run_time_s,
        **governance_context_meta,
        "generate_success_count": generate_success_count,
        "syntax_success_count": syntax_success_count,
        "pytest_success_count": pytest_success_count,
        "fix_retry_count": fix_retry_count,
        "pytest_passed_case_count": pytest_passed_case_count,
        "pytest_failed_case_count": pytest_failed_case_count,
        "pytest_error_case_count": pytest_error_case_count,
        "pytest_skipped_case_count": pytest_skipped_case_count,
        "pytest_total_case_count": pytest_total_case_count,
        "pytest_executable_case_count": pytest_executable_case_count,
        "script_executable_rate": script_executable_rate,
        "pytest_case_pass_rate": pytest_case_pass_rate,
        "total_normal_case_count": total_normal_case_count,
        "total_exception_case_count": total_exception_case_count,
        "overall_exception_case_rate": overall_exception_case_rate,
        "log_hit_count": log_hit_count,
        "code_hit_count": code_hit_count,
        "generate_success_rate": rate(generate_success_count),
        "syntax_success_rate": rate(syntax_success_count),
        "pytest_success_rate": rate(pytest_success_count),
    }
    write_run_config(run_dir, run_info)
    append_history(run_info)

    print(f"生成总耗时：{total_generate_time_s} 秒")
    print(f"接口生成耗时累计：{sum_endpoint_generate_time_s} 秒")
    print(f"本次运行总耗时：{total_run_time_s} 秒")
    print(f"测试脚本目录：{os.path.abspath(tests_dir)}")
    print(f"pytest执行明细目录：{os.path.abspath(reports_dir)}")
    print(f"汇总结果：{os.path.abspath(summary_file)}")
    print(f"本轮报告Excel：{os.path.abspath(run_report_xlsx)}")
    print(f"运行配置：{os.path.abspath(os.path.join(run_dir, 'run_config.json'))}")
    print(f"历史索引：{os.path.join(RUNS_DIR, 'history.csv')}")
    return run_info


def _has_log_case(log_map: Dict[str, List[Dict[str, Any]]], method: str, path: str) -> bool:
    """检查是否存在日志用例。"""
    from core.parsers.log_parser import find_log_cases_for_endpoint
    return bool(find_log_cases_for_endpoint(log_map, method, path))


def main(spec: str, mode: str = None, exception_mode: str = None, repeat: int = 1, **kwargs) -> None:
    """主入口函数。
    
    Args:
        spec: Swagger 文件路径
        mode: 生成模式
        exception_mode: 异常用例模式
        repeat: 重复执行次数
        **kwargs: 其他参数传递给 run_once
    """
    run_infos = []
    for i in range(repeat):
        repeat_index = i + 1
        run_info = run_once(
            spec,
            mode=mode,
            exception_mode=exception_mode,
            repeat_index=repeat_index,
            repeat_total=repeat,
            **kwargs
        )
        run_infos.append(run_info)
    
    if repeat > 1:
        write_repeat_summary(mode or "swagger", exception_mode or "basic", run_infos)


def write_repeat_summary(mode: str, exception_mode: str, run_infos: List[Dict[str, Any]]) -> None:
    """写入多轮运行汇总报告。"""
    import csv
    if not run_infos:
        return

    os.makedirs(RUNS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    base_name = f"repeat_{timestamp}_{mode}_{exception_mode}_{len(run_infos)}runs"
    csv_path = os.path.join(RUNS_DIR, f"{base_name}.csv")
    txt_path = os.path.join(RUNS_DIR, f"{base_name}.txt")

    fields = [
        ("run_id", "运行ID"),
        ("mode", "生成模式"),
        ("exception_mode", "异常用例模式"),
        ("swagger_count", "Swagger接口数"),
        ("generated_count", "生成接口数"),
        ("generate_success_rate", "生成成功率"),
        ("syntax_success_rate", "语法通过率"),
        ("pytest_success_rate", "pytest接口通过率"),
        ("total_generate_time_s", "生成总耗时秒"),
        ("sum_endpoint_generate_time_s", "接口生成耗时累计秒"),
        ("total_run_time_s", "运行总耗时秒"),
        ("governance_context_used", "是否使用规范扫描上下文"),
        ("governance_context_chars", "规范扫描上下文字数"),
        ("governance_context_source", "规范扫描上下文来源"),
        ("fix_retry_count", "生成代码后处理次数"),
        ("pytest_passed_case_count", "pytest用例通过数"),
        ("pytest_failed_case_count", "pytest用例失败数"),
        ("pytest_error_case_count", "pytest用例错误数"),
        ("pytest_skipped_case_count", "pytest用例跳过数"),
        ("pytest_total_case_count", "pytest用例总数"),
        ("pytest_executable_case_count", "脚本可执行用例数"),
        ("script_executable_rate", "脚本可执行率"),
        ("pytest_case_pass_rate", "pytest用例通过率"),
        ("total_normal_case_count", "正常用例数"),
        ("total_exception_case_count", "异常用例数"),
        ("overall_exception_case_rate", "异常用例占比"),
        ("log_hit_count", "日志命中接口数"),
        ("code_hit_count", "代码扫描命中接口数"),
        ("run_dir", "运行目录"),
    ]

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([title for _, title in fields])
        for info in run_infos:
            writer.writerow([info.get(key, "") for key, _ in fields])

    def avg(key: str) -> float:
        values = [float(info.get(key, 0) or 0) for info in run_infos]
        return round(sum(values) / len(values), 2) if values else 0.0

    text = [
        "=== 多轮运行汇总 ===",
        f"模式：{mode}",
        f"异常用例模式：{exception_mode}",
        f"运行轮数：{len(run_infos)}",
        f"平均生成成功率：{avg('generate_success_rate')}%",
        f"平均语法通过率：{avg('syntax_success_rate')}%",
        f"平均pytest通过率：{avg('pytest_success_rate')}%",
        f"平均pytest用例通过数：{avg('pytest_passed_case_count')}",
        f"平均pytest用例失败数：{avg('pytest_failed_case_count')}",
        f"平均pytest用例错误数：{avg('pytest_error_case_count')}",
        f"平均脚本可执行率：{avg('script_executable_rate')}%",
        f"平均pytest用例通过率：{avg('pytest_case_pass_rate')}%",
        f"平均生成总耗时：{avg('total_generate_time_s')} 秒",
        f"平均运行总耗时：{avg('total_run_time_s')} 秒",
        f"平均修复次数：{avg('fix_retry_count')}",
        f"平均异常用例数：{avg('total_exception_case_count')}",
        f"平均异常用例占比：{avg('overall_exception_case_rate')}%",
        f"平均日志命中接口数：{avg('log_hit_count')}",
        f"平均代码扫描命中接口数：{avg('code_hit_count')}",
        "",
        f"明细CSV：{csv_path}",
    ]
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(text) + "\n")

    print("\n" + "\n".join(text))
