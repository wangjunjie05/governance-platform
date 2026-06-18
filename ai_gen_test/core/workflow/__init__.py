"""测试生成器模块。

包含配置验证、上下文收集、代码生成、接口生成和主运行流程。
"""
from .config_validator import (
    normalize_generation_mode,
    normalize_exception_mode,
    normalize_path_filters,
    normalize_code_filters,
    endpoint_allowed,
    filter_endpoints,
    get_requested_knowledge_base,
    get_actual_knowledge_base,
    get_knowledge_base,
    detect_data_source,
    _split_csv,
)

from .context_collector import (
    collect_context,
    is_rule_executable_exception,
    count_success_log_cases,
    has_normal_case_rows,
)

from .code_generator import (
    generate_code,
    try_fix_code_once,
    save_code,
    strip_rule_cases,
    ensure_success_baseline,
    attach_rule_cases,
    attach_normal_baseline,
)

from .endpoint_generator import (
    generate_one_endpoint,
)

from .main_runner import (
    main,
    print_startup_info,
    make_run_dir,
    write_run_config,
    append_history,
    run_once,
    write_repeat_summary,
)

__all__ = [
    # main entry
    "main",
    # config_validator
    "normalize_generation_mode",
    "normalize_exception_mode",
    "normalize_path_filters",
    "normalize_code_filters",
    "endpoint_allowed",
    "filter_endpoints",
    "get_requested_knowledge_base",
    "get_actual_knowledge_base",
    "get_knowledge_base",
    "detect_data_source",
    "_split_csv",
    # context_collector
    "collect_context",
    "is_rule_executable_exception",
    "count_success_log_cases",
    "has_normal_case_rows",
    # code_generator
    "generate_code",
    "try_fix_code_once",
    "save_code",
    "strip_rule_cases",
    "ensure_success_baseline",
    "attach_rule_cases",
    "attach_normal_baseline",
    # endpoint_generator
    "generate_one_endpoint",
    # main_runner
    "print_startup_info",
    "make_run_dir",
    "write_run_config",
    "append_history",
    "run_once",
    "write_repeat_summary",
]
