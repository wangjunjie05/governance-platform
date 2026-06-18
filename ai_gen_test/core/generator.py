"""
测试生成器模块 - 兼容层

此文件保留原有的导入接口，内部已重构为多个子模块。
原有代码已拆分到 core/workflow/ 目录下的多个模块中：
- config_validator.py: 配置验证和参数标准化
- context_collector.py: 上下文信息收集
- code_generator.py: 代码生成核心逻辑
- endpoint_generator.py: 单个接口生成流程
- main_runner.py: 主运行流程

此文件保持向后兼容，所有原有导入路径继续有效。
"""
from .workflow import (
    # main entry
    main,
    # config_validator
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
    # context_collector
    collect_context,
    is_rule_executable_exception,
    count_success_log_cases,
    has_normal_case_rows,
    # code_generator
    generate_code,
    try_fix_code_once,
    save_code,
    strip_rule_cases,
    ensure_success_baseline,
    attach_rule_cases,
    attach_normal_baseline,
    # endpoint_generator
    generate_one_endpoint,
    # main_runner
    print_startup_info,
    make_run_dir,
    write_run_config,
    append_history,
    run_once,
    write_repeat_summary,
)

__all__ = [
    "main",
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
    "collect_context",
    "is_rule_executable_exception",
    "count_success_log_cases",
    "has_normal_case_rows",
    "generate_code",
    "try_fix_code_once",
    "save_code",
    "strip_rule_cases",
    "ensure_success_baseline",
    "attach_rule_cases",
    "attach_normal_baseline",
    "generate_one_endpoint",
    "print_startup_info",
    "make_run_dir",
    "write_run_config",
    "append_history",
    "run_once",
    "write_repeat_summary",
]
